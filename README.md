# CelesteOS Registration API (Windows-Compatible)

Backend service handling the complete yacht onboarding flow — from download portal to software activation. Supports both macOS and Windows agents.

## What This Does

This service handles:

1. **Yacht Registration** — Installer contacts this service on first launch, triggering a 2FA verification email
2. **2FA Verification** — Validates the 6-digit code, returns a cryptographic secret for ongoing authentication
3. **Download Portal** — Web page where buyers enter their email, verify with a code, and download the installer
4. **Health Monitoring** — Simple health check endpoint

## Architecture

```
Buyer visits download.celeste7.ai
  → Enters email
  → Receives 6-digit code (via Microsoft Graph API)
  → Enters code
  → Downloads installer (DMG for macOS, EXE for Windows)

Buyer installs and launches CelesteOS
  → App calls POST /api/register
  → Buyer receives 6-digit code by email
  → Enters code in app
  → App calls POST /api/verify-2fa → receives shared_secret
  → Secret stored in platform credential store (Keychain on macOS, Credential Manager on Windows)
  → App is now activated
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/register` | Register yacht, send 2FA code to buyer email |
| POST | `/api/verify-2fa` | Verify code, return shared_secret (one-time) |
| POST | `/api/request-download-code` | Send download verification code |
| POST | `/api/verify-download-code` | Verify download code, return download URL |
| GET | `/api/health` | Health check |
| GET | `/` | Download portal (static HTML) |

## Platform Support

All endpoints are **fully cross-platform**. The registration service makes zero assumptions about the client's operating system. Both macOS and Windows agents call the same API identically.

The only platform difference is in the download portal, which serves different installer files based on the yacht's configuration:
- macOS: `.dmg` (disk image, drag to Applications)
- Windows: `.exe` (Inno Setup installer)

The storage path is read from `fleet_registry.dmg_storage_path` (or `exe_storage_path` for Windows) — no code changes needed per platform.

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (copy .env.example to .env)
cp .env.example .env
# Edit .env with your credentials

# Start the service
python -m uvicorn services.registration:app --host 0.0.0.0 --port 8001

# Or via Docker
docker compose up --build
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `MASTER_SUPABASE_URL` | Yes | Master Supabase project URL |
| `MASTER_SUPABASE_SERVICE_KEY` | Yes | Supabase service role JWT |
| `AZURE_TENANT_ID` | No* | Microsoft Azure AD tenant ID |
| `AZURE_CLIENT_ID` | No* | Azure app registration client ID |
| `AZURE_CLIENT_SECRET` | No* | Azure app client secret |
| `AZURE_SENDER_EMAIL` | No* | Email address to send from (must be a real mailbox) |

*When Azure credentials are not set, the service runs in **debug mode** — verification codes are logged to the console instead of sent by email. All other functionality works identically.

## Database

Uses the **master** Supabase instance (`qvzmkaamzaqxpzbewjxe`). Required tables:

- `fleet_registry` — Yacht records with buyer email, activation state
- `installation_2fa_codes` — Hashed verification codes with expiry and attempt tracking
- `download_links` — Time-limited download tokens

Migrations are in `supabase/migrations/`. The `installation_2fa_codes` table is separate from the user-account `twofa_codes` table (different schema, different purpose).

## Security

- 2FA codes are SHA-256 hashed before storage
- Code comparison uses constant-time comparison (prevents timing attacks)
- Codes expire after 10 minutes
- Maximum 5 attempts per code before lockout
- CORS restricted to specific portal domains
- Download tokens are hashed for Edge Function compatibility
- Shared secrets are 256-bit cryptographically random

## Related Repos

- [`Celesteos-agent-windows`](https://github.com/shortalex12333/Celesteos-agent-windows) — Cross-platform agent (macOS + Windows) that runs on the yacht
- [`celesteos-agent`](https://github.com/shortalex12333/celesteos-agent) — Original macOS-only agent
- `Cloud_PMS` — The main yacht management system (search, lenses, actions)
