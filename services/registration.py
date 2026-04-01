"""
CelesteOS Registration API
============================
FastAPI service handling the complete installation + download flow.
Replaces the n8n webhook layer with direct Python endpoints.

Endpoints:
    POST /api/register            — Yacht registration (triggers 2FA email)
    POST /api/verify-2fa          — Verify 2FA code → return shared_secret
    POST /api/request-download-code — Send download 2FA code to buyer email
    POST /api/verify-download-code  — Verify download code → return download URL
    GET  /api/health              — Health check
"""

import hashlib
import logging
import os
import secrets
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr

import httpx

logger = logging.getLogger("services.registration")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MASTER_SUPABASE_URL = os.getenv(
    "MASTER_SUPABASE_URL", "https://qvzmkaamzaqxpzbewjxe.supabase.co"
)
MASTER_SUPABASE_KEY = os.getenv("MASTER_SUPABASE_SERVICE_KEY", "")

TWOFA_EXPIRY_MINUTES = 10
TWOFA_MAX_ATTEMPTS = 5

# ---------------------------------------------------------------------------
# Supabase REST helper
# ---------------------------------------------------------------------------

def _sb_headers() -> dict:
    return {
        "apikey": MASTER_SUPABASE_KEY,
        "Authorization": f"Bearer {MASTER_SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_url(path: str) -> str:
    return f"{MASTER_SUPABASE_URL}/rest/v1/{path}"


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    yacht_id: str
    yacht_id_hash: str


class Verify2FARequest(BaseModel):
    yacht_id: str
    code: str


class RequestDownloadCodeRequest(BaseModel):
    email: str  # EmailStr requires email-validator; keep it simple


class VerifyDownloadCodeRequest(BaseModel):
    email: str
    code: str


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="CelesteOS Registration API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://registration.celeste7.ai",
        "https://download.celeste7.ai",
        "http://localhost:8001",  # local dev (portal served by same FastAPI)
        "http://localhost:8080",  # local dev alt
    ],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)


# Late-import email service so env vars are read at startup
_email_service = None

def _get_email():
    global _email_service
    if _email_service is None:
        from .email import GraphEmailService
        _email_service = GraphEmailService()
    return _email_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_code() -> str:
    """Generate a 6-digit 2FA code."""
    return f"{secrets.randbelow(1000000):06d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _mask_email(email: str) -> str:
    """b***@example.com"""
    local, _, domain = email.partition("@")
    if len(local) <= 1:
        return f"*@{domain}"
    return f"{local[0]}***@{domain}"


async def _store_2fa(
    yacht_id: str,
    code_hash: str,
    email: str,
    purpose: str = "installation",
) -> None:
    """Insert a 2FA code row into installation_2fa_codes."""
    expires = (datetime.now(timezone.utc) + timedelta(minutes=TWOFA_EXPIRY_MINUTES)).isoformat()
    payload = {
        "yacht_id": yacht_id,
        "code_hash": code_hash,
        "email_sent_to": email,
        "purpose": purpose,
        "expires_at": expires,
        "verified": False,
        "attempts": 0,
        "max_attempts": TWOFA_MAX_ATTEMPTS,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(_sb_url("installation_2fa_codes"), json=payload, headers=_sb_headers(), timeout=15)
        if resp.status_code not in (200, 201):
            logger.error("Failed to store 2FA code: %d %s", resp.status_code, resp.text)
            raise HTTPException(500, "Failed to store verification code")


async def _validate_2fa(
    yacht_id: str,
    code: str,
    purpose: str = "installation",
) -> dict:
    """
    Validate a 2FA code. Returns the installation_2fa_codes row if valid.
    Raises HTTPException on failure.
    """
    code_hash = _hash_code(code)

    async with httpx.AsyncClient() as client:
        # Find latest unexpired, unverified code for this yacht + purpose
        params = {
            "yacht_id": f"eq.{yacht_id}",
            "purpose": f"eq.{purpose}",
            "verified": "eq.false",
            "expires_at": f"gte.{datetime.now(timezone.utc).isoformat()}",
            "order": "created_at.desc",
            "limit": "1",
        }
        resp = await client.get(
            _sb_url("installation_2fa_codes"),
            params=params,
            headers=_sb_headers(),
            timeout=15,
        )
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(400, {"success": False, "error": "No valid code found or code expired"})

        row = resp.json()[0]

        # Check attempts
        if row["attempts"] >= row["max_attempts"]:
            raise HTTPException(400, {"success": False, "error": "Too many attempts. Request a new code."})

        # Increment attempts
        await client.patch(
            _sb_url(f"installation_2fa_codes?id=eq.{row['id']}"),
            json={"attempts": row["attempts"] + 1},
            headers={**_sb_headers(), "Prefer": "return=minimal"},
            timeout=15,
        )

        # Compare hash (constant-time via hmac.compare_digest equivalent)
        if not secrets.compare_digest(code_hash, row["code_hash"]):
            remaining = row["max_attempts"] - row["attempts"] - 1
            raise HTTPException(400, {
                "success": False,
                "error": "Invalid code",
                "attempts_remaining": max(remaining, 0),
            })

        # Mark verified
        await client.patch(
            _sb_url(f"installation_2fa_codes?id=eq.{row['id']}"),
            json={"verified": True, "verified_at": datetime.now(timezone.utc).isoformat()},
            headers={**_sb_headers(), "Prefer": "return=minimal"},
            timeout=15,
        )

        return row


async def _get_yacht(yacht_id: str) -> Optional[dict]:
    """Fetch yacht from fleet_registry."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _sb_url("fleet_registry"),
            params={"yacht_id": f"eq.{yacht_id}", "select": "*"},
            headers=_sb_headers(),
            timeout=15,
        )
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    return None


async def _get_yacht_by_email(email: str) -> Optional[dict]:
    """Find yacht by buyer_email."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _sb_url("fleet_registry"),
            params={"buyer_email": f"eq.{email}", "select": "*"},
            headers=_sb_headers(),
            timeout=15,
        )
        if resp.status_code == 200 and resp.json():
            return resp.json()[0]
    return None


async def _update_yacht(yacht_id: str, data: dict) -> None:
    """Patch fleet_registry row."""
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            _sb_url(f"fleet_registry?yacht_id=eq.{yacht_id}"),
            json=data,
            headers={**_sb_headers(), "Prefer": "return=minimal"},
            timeout=15,
        )
        if resp.status_code not in (200, 204):
            logger.error("fleet_registry update failed: %d %s", resp.status_code, resp.text)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "registration-api", "timestamp": int(time.time())}


@app.post("/api/register")
async def register(req: RegisterRequest):
    """
    Yacht registration — triggered by the installer on first launch.
    Validates yacht_id_hash, sends 2FA code to buyer_email.
    """
    # 1. Validate yacht exists
    yacht = await _get_yacht(req.yacht_id)
    if not yacht:
        raise HTTPException(404, {"success": False, "error": "Yacht not found"})

    # 2. Validate hash
    expected_hash = hashlib.sha256(req.yacht_id.encode("utf-8")).hexdigest()
    if not secrets.compare_digest(expected_hash, req.yacht_id_hash):
        raise HTTPException(400, {"success": False, "error": "Invalid yacht identity"})

    buyer_email = yacht.get("buyer_email")
    if not buyer_email:
        raise HTTPException(400, {"success": False, "error": "No buyer email on record"})

    # 3. Generate + store 2FA code
    code = _generate_code()
    await _store_2fa(req.yacht_id, _hash_code(code), buyer_email, purpose="installation")

    # 4. Send email
    yacht_name = yacht.get("yacht_name", req.yacht_id)
    email_svc = _get_email()
    sent = email_svc.send_2fa_code(buyer_email, code, yacht_name)

    if not sent:
        raise HTTPException(502, {"success": False, "error": "Failed to send verification email"})

    # 5. Update fleet_registry
    await _update_yacht(req.yacht_id, {"registered_at": datetime.now(timezone.utc).isoformat()})

    logger.info("Registration 2FA sent for yacht %s to %s", req.yacht_id, _mask_email(buyer_email))

    return {
        "success": True,
        "email_sent_to": _mask_email(buyer_email),
        "message": "Verification code sent. Check your email.",
    }


@app.post("/api/verify-2fa")
async def verify_2fa(req: Verify2FARequest):
    """
    Verify 2FA code from the installer.
    On success: generates shared_secret, activates yacht, returns secret (one-time).
    """
    # Validate code
    await _validate_2fa(req.yacht_id, req.code, purpose="installation")

    # Generate shared_secret
    shared_secret = secrets.token_hex(32)  # 256-bit

    # Activate yacht
    await _update_yacht(req.yacht_id, {
        "active": True,
        "shared_secret": shared_secret,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "credentials_retrieved": True,
    })

    # Fetch tenant credentials to return to the agent
    yacht = await _get_yacht(req.yacht_id)
    tenant_url = yacht.get("tenant_supabase_url", "") if yacht else ""
    tenant_key = yacht.get("tenant_supabase_service_key", "") if yacht else ""

    logger.info("Yacht %s activated via 2FA", req.yacht_id)

    return {
        "success": True,
        "shared_secret": shared_secret,
        "supabase_url": tenant_url,
        "supabase_service_key": tenant_key,
    }


@app.post("/api/request-download-code")
async def request_download_code(req: RequestDownloadCodeRequest):
    """
    Download portal step 1 — send 2FA code to buyer's email.
    """
    yacht = await _get_yacht_by_email(req.email)
    if not yacht:
        # Don't reveal whether the email exists — always return success
        logger.info("Download code requested for unknown email: %s", _mask_email(req.email))
        return {"success": True}

    code = _generate_code()
    await _store_2fa(
        yacht["yacht_id"],
        _hash_code(code),
        req.email,
        purpose="download",
    )

    yacht_name = yacht.get("yacht_name", yacht["yacht_id"])
    email_svc = _get_email()
    email_svc.send_download_code(req.email, code, yacht_name)

    logger.info("Download code sent for yacht %s to %s", yacht["yacht_id"], _mask_email(req.email))
    return {"success": True}


@app.post("/api/verify-download-code")
async def verify_download_code(req: VerifyDownloadCodeRequest):
    """
    Download portal step 2 — verify code, return download URL.
    """
    yacht = await _get_yacht_by_email(req.email)
    if not yacht:
        raise HTTPException(400, {"success": False, "error": "Invalid code"})

    await _validate_2fa(yacht["yacht_id"], req.code, purpose="download")

    # Generate a time-limited download token and store in download_links
    download_token = secrets.token_hex(32)
    # Edge Function looks up by token_hash = SHA-256(raw_token)
    token_hash = hashlib.sha256(download_token.encode("utf-8")).hexdigest()
    twofa_code = secrets.token_hex(8)  # internal ref, not user-facing
    dmg_path = yacht.get("dmg_storage_path") or f"dmg/{yacht['yacht_id']}/CelesteOS-{yacht['yacht_id']}.dmg"
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            _sb_url("download_links"),
            json={
                "yacht_id": yacht["yacht_id"],
                "download_token": download_token,
                "token_hash": token_hash,
                "twofa_code": twofa_code,
                "package_path": dmg_path,
                "platform": yacht.get("installer_type", "dmg"),
                "is_activation_link": False,
                "expires_at": expires,
                "download_count": 0,
            },
            headers=_sb_headers(),
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            logger.error("Failed to create download link: %d %s", resp.status_code, resp.text)
            raise HTTPException(500, {"success": False, "error": "Failed to generate download link"})

    # Generate a signed Storage URL (1 hour expiry) — browser can download directly
    async with httpx.AsyncClient() as client:
        sign_resp = await client.post(
            f"{MASTER_SUPABASE_URL}/storage/v1/object/sign/installers/{dmg_path}",
            json={"expiresIn": 3600},
            headers=_sb_headers(),
            timeout=15,
        )
        if sign_resp.status_code == 200:
            signed_path = sign_resp.json().get("signedURL", "")
            download_url = f"{MASTER_SUPABASE_URL}/storage/v1{signed_path}"
        else:
            logger.error("Failed to sign URL: %d %s", sign_resp.status_code, sign_resp.text)
            # Fallback to Edge Function
            download_url = f"{MASTER_SUPABASE_URL}/functions/v1/download?token={download_token}"

    yacht_name = yacht.get("yacht_name", yacht["yacht_id"])

    logger.info("Download token generated for yacht %s", yacht["yacht_id"])

    return {
        "success": True,
        "download_url": download_url,
        "yacht_name": yacht_name,
    }


# ---------------------------------------------------------------------------
# Welcome email (admin-triggered)
# ---------------------------------------------------------------------------

PORTAL_BASE_URL = os.getenv("PORTAL_BASE_URL", "https://registration.celeste7.ai")


class SendWelcomeRequest(BaseModel):
    yacht_id: str
    admin_key: Optional[str] = None  # simple guard — not a full auth system


ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")


@app.post("/api/send-welcome")
async def send_welcome(req: SendWelcomeRequest, request: Request):
    """Send the welcome email with download portal link to the buyer."""
    # Simple admin guard
    if ADMIN_KEY and req.admin_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Look up yacht
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            _sb_url(f"fleet_registry?yacht_id=eq.{req.yacht_id}&select=yacht_name,buyer_email,active"),
            headers=_sb_headers(),
        )
    if resp.status_code != 200 or not resp.json():
        raise HTTPException(status_code=404, detail="Yacht not found")

    yacht = resp.json()[0]
    if not yacht.get("active"):
        raise HTTPException(status_code=400, detail="Yacht is not active")
    if not yacht.get("buyer_email"):
        raise HTTPException(status_code=400, detail="No buyer email on record")

    buyer_email = yacht["buyer_email"]
    yacht_name = yacht["yacht_name"]

    # Build portal URL with pre-filled email
    import urllib.parse
    portal_url = f"{PORTAL_BASE_URL}?email={urllib.parse.quote(buyer_email)}"

    email_svc = _get_email()
    sent = email_svc.send_welcome_email(buyer_email, yacht_name, portal_url)

    if not sent:
        raise HTTPException(status_code=500, detail="Failed to send welcome email")

    logger.info("Welcome email sent for %s to %s", req.yacht_id, _mask_email(buyer_email))
    return {"success": True, "sent_to": _mask_email(buyer_email)}


# ---------------------------------------------------------------------------
# Serve download portal as static page
# ---------------------------------------------------------------------------

PORTAL_DIR = Path(__file__).parent.parent / "portal"

if PORTAL_DIR.is_dir():
    @app.get("/", response_class=HTMLResponse)
    async def portal_home():
        download_page = PORTAL_DIR / "download.html"
        if download_page.exists():
            return HTMLResponse(
                download_page.read_text(),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        # Fall back to status page
        index_page = PORTAL_DIR / "index.html"
        if index_page.exists():
            return HTMLResponse(index_page.read_text())
        return HTMLResponse("<h1>CelesteOS Portal</h1>")
