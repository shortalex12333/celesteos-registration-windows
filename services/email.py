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
        subject = f"Welcome to CelesteOS — {yacht_name}"
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
<body style="margin:0;padding:0;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:12px;padding:40px;border:1px solid rgba(148,163,184,0.15);">
        <tr><td style="color:#e2e8f0;font-size:24px;font-weight:700;padding-bottom:8px;">CelesteOS</td></tr>
        <tr><td style="color:#94a3b8;font-size:14px;padding-bottom:32px;">Yacht Management System</td></tr>
        <tr><td style="color:#e2e8f0;font-size:16px;padding-bottom:24px;">
          Your verification code for <strong style="color:#60a5fa;">{yacht_name}</strong>:
        </td></tr>
        <tr><td align="center" style="padding-bottom:24px;">
          <div style="display:inline-block;background:#0f172a;border:2px solid #3b82f6;border-radius:8px;padding:16px 32px;font-size:32px;letter-spacing:8px;color:#60a5fa;font-weight:700;">
            {code}
          </div>
        </td></tr>
        <tr><td style="color:#94a3b8;font-size:14px;padding-bottom:16px;">
          Enter this code in the CelesteOS installer to complete activation.
          This code expires in <strong>10 minutes</strong>.
        </td></tr>
        <tr><td style="color:#64748b;font-size:12px;border-top:1px solid rgba(148,163,184,0.1);padding-top:16px;">
          If you did not request this code, please ignore this email.
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
<body style="margin:0;padding:0;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:12px;padding:40px;border:1px solid rgba(148,163,184,0.15);">
        <tr><td style="color:#e2e8f0;font-size:24px;font-weight:700;padding-bottom:8px;">CelesteOS</td></tr>
        <tr><td style="color:#94a3b8;font-size:14px;padding-bottom:32px;">Yacht Management System</td></tr>
        <tr><td style="color:#e2e8f0;font-size:16px;padding-bottom:16px;">
          Welcome aboard, <strong style="color:#60a5fa;">{yacht_name}</strong>.
        </td></tr>
        <tr><td style="color:#94a3b8;font-size:14px;padding-bottom:24px;line-height:1.6;">
          Your CelesteOS installation is ready. Click the button below to download
          and install the system on your vessel's computer. You'll be asked to verify
          your email with a one-time code during the process.
        </td></tr>
        <tr><td align="center" style="padding-bottom:32px;">
          <a href="{portal_url}" style="display:inline-block;background:#3b82f6;color:#ffffff;font-size:16px;font-weight:600;padding:14px 32px;border-radius:8px;text-decoration:none;letter-spacing:0.5px;">
            Download CelesteOS
          </a>
        </td></tr>
        <tr><td style="color:#94a3b8;font-size:13px;padding-bottom:16px;line-height:1.5;">
          <strong>What happens next:</strong><br/>
          1. Click the button above to open the download portal<br/>
          2. Enter your email address to receive a verification code<br/>
          3. Enter the code to start the download<br/>
          4. Open the installer and follow the on-screen steps
        </td></tr>
        <tr><td style="color:#64748b;font-size:12px;border-top:1px solid rgba(148,163,184,0.1);padding-top:16px;">
          This link is unique to {yacht_name}. Do not forward this email.<br/>
          If you have questions, reply to this email or contact support@celeste7.ai
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
<body style="margin:0;padding:0;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:40px 0;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:12px;padding:40px;border:1px solid rgba(148,163,184,0.15);">
        <tr><td style="color:#e2e8f0;font-size:24px;font-weight:700;padding-bottom:8px;">CelesteOS</td></tr>
        <tr><td style="color:#94a3b8;font-size:14px;padding-bottom:32px;">Download Portal</td></tr>
        <tr><td style="color:#e2e8f0;font-size:16px;padding-bottom:24px;">
          Your download verification code for <strong style="color:#60a5fa;">{yacht_name}</strong>:
        </td></tr>
        <tr><td align="center" style="padding-bottom:24px;">
          <div style="display:inline-block;background:#0f172a;border:2px solid #3b82f6;border-radius:8px;padding:16px 32px;font-size:32px;letter-spacing:8px;color:#60a5fa;font-weight:700;">
            {code}
          </div>
        </td></tr>
        <tr><td style="color:#94a3b8;font-size:14px;padding-bottom:16px;">
          Enter this code on the download page to access your CelesteOS installer.
          This code expires in <strong>10 minutes</strong>.
        </td></tr>
        <tr><td style="color:#64748b;font-size:12px;border-top:1px solid rgba(148,163,184,0.1);padding-top:16px;">
          If you did not request this code, please ignore this email.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
