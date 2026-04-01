"""
Microsoft Graph API Email Service
==================================
Sends branded emails via Microsoft Graph using client_credentials grant.

Debug mode: when AZURE_TENANT_ID is not set, logs the email content
(including 2FA codes) to the console instead of sending. This allows
the full registration flow to be tested without Azure credentials.
"""

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger("services.email")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")
AZURE_SENDER_EMAIL = os.getenv("AZURE_SENDER_EMAIL", "noreply@celeste7.ai")
LOGO_URL = os.getenv("CELESTEOS_LOGO_URL", "https://celeste7.ai/favicon.png")


class GraphEmailService:
    """Send emails via Microsoft Graph API with automatic token refresh."""

    TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    SEND_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
    TOKEN_REFRESH_MARGIN = 300  # refresh 5 min before expiry

    def __init__(
        self,
        tenant_id: str = AZURE_TENANT_ID,
        client_id: str = AZURE_CLIENT_ID,
        client_secret: str = AZURE_CLIENT_SECRET,
        sender_email: str = AZURE_SENDER_EMAIL,
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.sender_email = sender_email

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

        self.debug_mode = not self.tenant_id
        if self.debug_mode:
            logger.warning(
                "AZURE_TENANT_ID not set — email service running in DEBUG mode "
                "(codes will be logged to console, no emails sent)"
            )

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------
    def _refresh_token(self) -> None:
        """Obtain or refresh the OAuth2 access token."""
        url = self.TOKEN_URL.format(tenant=self.tenant_id)
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }
        resp = httpx.post(url, data=data, timeout=15)
        resp.raise_for_status()
        body = resp.json()

        self._access_token = body["access_token"]
        self._token_expires_at = time.time() + body.get("expires_in", 3600)
        logger.info("Graph API token refreshed, expires in %ds", body.get("expires_in", 3600))

    def _ensure_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if (
            self._access_token is None
            or time.time() >= self._token_expires_at - self.TOKEN_REFRESH_MARGIN
        ):
            self._refresh_token()
        return self._access_token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------
    def send_email(self, to: str, subject: str, html_body: str) -> bool:
        """
        Send an email via Graph API.

        Returns True on success. In debug mode, logs the email and returns True.
        """
        if self.debug_mode:
            logger.info("DEBUG EMAIL — to: %s | subject: %s", to, subject)
            return True

        token = self._ensure_token()
        url = self.SEND_URL.format(sender=self.sender_email)

        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "HTML", "content": html_body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": "false",
        }

        resp = httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )

        if resp.status_code == 202:
            logger.info("Email sent to %s: %s", to, subject)
            return True

        logger.error("Graph API send failed: %d %s", resp.status_code, resp.text)
        return False

    # ------------------------------------------------------------------
    # Branded templates
    # ------------------------------------------------------------------
    def send_2fa_code(self, to: str, code: str, yacht_name: str) -> bool:
        """Send a branded 2FA verification email."""
        if self.debug_mode:
            print(f"\n{'='*50}")
            print(f"  2FA CODE for {yacht_name}")
            print(f"  To: {to}")
            print(f"  Code: {code}")
            print(f"{'='*50}\n", flush=True)
        subject = f"CelesteOS — Your verification code"
        html = _render_2fa_template(code, yacht_name)
        return self.send_email(to, subject, html)

    def send_download_code(self, to: str, code: str, yacht_name: str) -> bool:
        """Send a download verification code."""
        if self.debug_mode:
            print(f"\n{'='*50}")
            print(f"  DOWNLOAD CODE for {yacht_name}")
            print(f"  To: {to}")
            print(f"  Code: {code}")
            print(f"{'='*50}\n", flush=True)
        subject = f"CelesteOS — Download verification code"
        html = _render_download_code_template(code, yacht_name)
        return self.send_email(to, subject, html)

    def send_welcome_email(self, to: str, yacht_name: str, portal_url: str) -> bool:
        """Send a branded welcome email with the download portal link."""
        if self.debug_mode:
            print(f"\n{'='*50}")
            print(f"  WELCOME EMAIL for {yacht_name}")
            print(f"  To: {to}")
            print(f"  Portal: {portal_url}")
            print(f"{'='*50}\n", flush=True)
        subject = f"CelesteOS — Installation ready — {yacht_name}"
        html = _render_welcome_template(yacht_name, portal_url)
        return self.send_email(to, subject, html)


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

def _render_2fa_template(code: str, yacht_name: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0c0b0a;font-family:-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0c0b0a;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#0c0b0a;text-align:center;">
        <tr><td style="height:60px;"></td></tr>
        <tr><td style="padding:0 48px 48px 48px;">
          <img src="{LOGO_URL}" alt="CelesteOS" width="32" height="32" style="border:0;" />
        </td></tr>
        <tr><td style="padding:0 48px 12px 48px;color:#5AABCC;font-size:13px;font-weight:500;letter-spacing:0.5px;">{yacht_name}</td></tr>
        <tr><td style="padding:0 48px 48px 48px;color:#eae6e1;font-size:15px;">Verification code</td></tr>
        <tr><td style="padding:0 48px 16px 48px;">
          <table align="center" cellpadding="0" cellspacing="0" style="background:#161412;border-radius:8px;">
            <tr><td style="padding:24px 40px;font-size:36px;letter-spacing:12px;color:#eae6e1;font-weight:600;font-family:'SF Mono',ui-monospace,'Fira Code',monospace;text-align:center;">
              {code}
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:0 48px;color:#6e6860;font-size:13px;">Expires in 10 minutes</td></tr>
        <tr><td style="height:64px;"></td></tr>
        <tr><td style="padding:0 48px;"><table width="100%" cellpadding="0" cellspacing="0"><tr><td style="height:1px;background:#1e1b18;"></td></tr></table></td></tr>
        <tr><td style="padding:24px 48px 60px 48px;color:#3d3832;font-size:12px;line-height:1.6;">
          Enter this code in the CelesteOS installer to complete activation.<br/>
          Code not requested by you — disregard this email.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _render_welcome_template(yacht_name: str, portal_url: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0c0b0a;font-family:-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0c0b0a;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#0c0b0a;text-align:center;">
        <tr><td style="height:60px;"></td></tr>
        <tr><td style="padding:0 48px 48px 48px;">
          <img src="{LOGO_URL}" alt="CelesteOS" width="32" height="32" style="border:0;" />
        </td></tr>
        <tr><td style="padding:0 48px 12px 48px;color:#5AABCC;font-size:13px;font-weight:500;letter-spacing:0.5px;">{yacht_name}</td></tr>
        <tr><td style="padding:0 48px 16px 48px;color:#eae6e1;font-size:15px;">Installation ready.</td></tr>
        <tr><td style="padding:0 48px 40px 48px;color:#6e6860;font-size:14px;line-height:1.7;">
          The CelesteOS installer is available for download.<br/>
          Email verification is required during the process.
        </td></tr>
        <tr><td style="padding:0 48px 48px 48px;">
          <a href="{portal_url}" style="display:inline-block;background:#3A7C9D;color:#ffffff;font-size:14px;font-weight:500;padding:14px 28px;border-radius:8px;text-decoration:none;">
            Access Download Portal
          </a>
        </td></tr>
        <tr><td style="padding:0 48px 0 48px;color:#3d3832;font-size:13px;line-height:2;">
          1. Open the download portal<br/>
          2. Verify your email with a one-time code<br/>
          3. Download the installer<br/>
          4. Run the installer and follow on-screen steps
        </td></tr>
        <tr><td style="height:64px;"></td></tr>
        <tr><td style="padding:0 48px;"><table width="100%" cellpadding="0" cellspacing="0"><tr><td style="height:1px;background:#1e1b18;"></td></tr></table></td></tr>
        <tr><td style="padding:24px 48px 60px 48px;color:#3d3832;font-size:12px;line-height:1.6;">
          This link is unique to {yacht_name}. Do not forward this email.<br/>
          Contact: support@celeste7.ai
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _render_download_code_template(code: str, yacht_name: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0c0b0a;font-family:-apple-system,BlinkMacSystemFont,system-ui,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0c0b0a;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#0c0b0a;text-align:center;">
        <tr><td style="height:60px;"></td></tr>
        <tr><td style="padding:0 48px 48px 48px;">
          <img src="{LOGO_URL}" alt="CelesteOS" width="32" height="32" style="border:0;" />
        </td></tr>
        <tr><td style="padding:0 48px 12px 48px;color:#5AABCC;font-size:13px;font-weight:500;letter-spacing:0.5px;">{yacht_name}</td></tr>
        <tr><td style="padding:0 48px 48px 48px;color:#eae6e1;font-size:15px;">Download verification code</td></tr>
        <tr><td style="padding:0 48px 16px 48px;">
          <table align="center" cellpadding="0" cellspacing="0" style="background:#161412;border-radius:8px;">
            <tr><td style="padding:24px 40px;font-size:36px;letter-spacing:12px;color:#eae6e1;font-weight:600;font-family:'SF Mono',ui-monospace,'Fira Code',monospace;text-align:center;">
              {code}
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="padding:0 48px;color:#6e6860;font-size:13px;">Expires in 10 minutes</td></tr>
        <tr><td style="height:64px;"></td></tr>
        <tr><td style="padding:0 48px;"><table width="100%" cellpadding="0" cellspacing="0"><tr><td style="height:1px;background:#1e1b18;"></td></tr></table></td></tr>
        <tr><td style="padding:24px 48px 60px 48px;color:#3d3832;font-size:12px;line-height:1.6;">
          Enter this code on the download portal to access the installer.<br/>
          Code not requested by you — disregard this email.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
