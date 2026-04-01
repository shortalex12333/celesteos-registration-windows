# CelesteOS Registration & Onboarding Service

Backend API for the complete yacht onboarding pipeline — from admin SQL insert to running agent on the customer's machine.

## The Full Onboarding Flow

```
ADMIN                          SYSTEM                         CUSTOMER
─────                          ──────                         ────────
1. SQL insert into             2. Build DMG via PyInstaller   5. Receives welcome email
   fleet_registry                 (bakes in service keys)        from contact@celeste7.ai
   (scripts/onboard_yacht.sql)
                               3. Upload DMG to Supabase      6. Clicks "Access Download Portal"
                                  Storage: installers/dmg/        → registration.celeste7.ai
                                  {yacht_id}/CelesteOS-
                                  {yacht_id}.dmg               7. Enters email → receives 2FA code

                               4. POST /api/send-welcome       8. Enters code → DMG download starts
                                  (triggers welcome email)
                                                               9. Opens DMG → installer wizard
                                                                  → enters 2FA → activates

                                                              10. Agent runs (tray icon, sync daemon)
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/send-welcome` | Send welcome email with download portal link (admin) |
| POST | `/api/request-download-code` | Send 6-digit download verification code to buyer |
| POST | `/api/verify-download-code` | Verify code → return signed DMG download URL |
| POST | `/api/register` | Yacht registration from installer (triggers 2FA email) |
| POST | `/api/verify-2fa` | Verify installer 2FA → return shared_secret (one-time) |
| GET | `/api/health` | Health check |
| GET | `/` | Download portal (fallback static HTML) |

## Email Templates

Three branded HTML emails sent from `contact@celeste7.ai` via Microsoft Graph API:

| Email | Trigger | Content |
|-------|---------|---------|
| **Welcome** | `POST /api/send-welcome` | "Installation ready" + "Access Download Portal" button linking to registration.celeste7.ai |
| **Download code** | `POST /api/request-download-code` | 6-digit code for download portal verification |
| **Installer 2FA** | `POST /api/register` | 6-digit code for installer activation |

Templates are in `services/email.py`. Brand tokens: background `#0c0b0a`, card `#181614`, teal accent `#3A7C9D`, text `#eae6e1`.

## Project Structure

```
services/
  registration.py    — FastAPI app, all endpoints, Supabase REST calls
  email.py           — GraphEmailService + 3 branded HTML email templates
  __init__.py

portal/
  download.html      — Fallback download portal (served at /)
  favicon.png

scripts/
  onboard_yacht.sql  — SQL template for inserting a new yacht into fleet_registry

supabase/
  functions/
    download/
      index.ts       — Edge Function for signed download URLs (fallback path)
  migrations/
    001_complete_schema.sql
    007_download_token_system.sql
    008_installation_tracking.sql
    009_installation_2fa_codes.sql
    010_tenant_credentials.sql
    011_yacht_id_uuid_format.sql

.env.example         — Environment variable template
Dockerfile           — Python 3.11, port 8001
docker-compose.yml   — Local dev with health check
```

## Database (Master Supabase)

All tables live in the **master** Supabase project (`qvzmkaamzaqxpzbewjxe`), NOT the tenant.

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `fleet_registry` | One row per yacht | yacht_id, yacht_name, buyer_email, active, shared_secret, tenant_supabase_url, installer_type |
| `installation_2fa_codes` | Hashed 2FA codes with expiry | code_hash (SHA-256), yacht_id, email_sent_to, purpose (installation\|download), expires_at, verified, attempts, max_attempts |
| `download_links` | Time-limited download tokens | token_hash (SHA-256), yacht_id, package_path, platform, expires_at, download_count |
| `audit_log` | All registration actions | yacht_id, action, details (JSONB), ip_address |

## Security

- 2FA codes: SHA-256 hashed before storage, constant-time comparison, 10-min expiry, max 5 attempts
- Download tokens: 256-bit random, hashed for storage, 24-hour expiry
- Service keys: baked into DMG at build time — never sent over the wire, never stored in fleet_registry
- Recovery key: AES-encrypted at rest using hardware UUID (on the customer's machine)
- CORS: restricted to registration.celeste7.ai, download.celeste7.ai, localhost
- Email: doesn't reveal whether an email exists in fleet_registry (always returns success)

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MASTER_SUPABASE_URL` | Yes | — | Master Supabase project URL |
| `MASTER_SUPABASE_SERVICE_KEY` | Yes | — | Supabase service role JWT |
| `AZURE_TENANT_ID` | No* | — | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | No* | — | Azure app registration client ID (Write app) |
| `AZURE_CLIENT_SECRET` | No* | — | Azure app client secret |
| `AZURE_SENDER_EMAIL` | No* | `noreply@celeste7.ai` | Sender email (must be a real mailbox in Azure) |
| `PORTAL_BASE_URL` | No | `https://registration.celeste7.ai` | Download portal URL for welcome email links |
| `ADMIN_API_KEY` | No | — | Simple guard for /api/send-welcome (if set, must match request) |
| `PORT` | No | `8001` | Server port |

*Without Azure credentials, the service runs in **debug mode** — codes are logged to console instead of emailed. All other functionality works identically.

## Running Locally

```bash
cp .env.example .env
# Edit .env with credentials

# Option A: Direct
pip install -r requirements.txt
python -m uvicorn services.registration:app --host 0.0.0.0 --port 8001

# Option B: Docker
docker compose up --build
```

## Deployment

**Production:** Render free tier (Docker)
- Service: `celesteos-registration-windows` on Render
- URL: `https://celesteos-registration-windows.onrender.com`
- Auto-deploys on push to main
- Health check: `/api/health`

**Download portal frontend:** Vercel
- Repo: `celesteos-portal` (React + Vite)
- URL: `https://registration.celeste7.ai`
- Env: `VITE_API_URL=https://celesteos-registration-windows.onrender.com`

**Email sender:** Microsoft 365 via Graph API
- Sender: `contact@celeste7.ai`
- Azure app: CelesteOS.Outlook.Write (`f0b8944b-8127-4f0f-8ed5-5487462df50c`)
- Tenant: `073af86c-74f3-422b-ad5c-a35d41fce4be`

## Onboarding Runbook (Step by Step)

### 1. Create the yacht record
```sql
-- Run in Supabase SQL Editor (master project)
-- Edit the marked values, then execute
-- See: scripts/onboard_yacht.sql
```

### 2. Build the DMG
```bash
# In the celesteos-agent repo
SUPABASE_SERVICE_KEY=<master-key> \
TENANT_SUPABASE_SERVICE_KEY=<this-yacht's-tenant-key> \
python build_dmg.py <yacht_id>
# Output: CelesteOS-<yacht_id>.dmg (32-37MB)
# Automatically uploads to Supabase Storage: installers/dmg/<yacht_id>/
```

### 3. Send the welcome email
```bash
curl -X POST https://celesteos-registration-windows.onrender.com/api/send-welcome \
  -H "Content-Type: application/json" \
  -d '{"yacht_id": "<yacht_id>"}'
```
Customer receives branded email with "Access Download Portal" button.

### 4. Customer self-service
Customer clicks portal link → enters email → receives 2FA code → enters code → DMG downloads → installs → activates. No admin action needed.

### 5. Verify activation
```sql
SELECT yacht_id, yacht_name, active, shared_secret IS NOT NULL as activated
FROM fleet_registry
WHERE yacht_id = '<yacht_id>';
-- active=true + activated=true means the customer completed installation
```

## Related Repos

| Repo | Purpose |
|------|---------|
| [`celesteos-agent`](https://github.com/shortalex12333/celesteos-agent) | macOS agent — installer GUI, sync daemon, tray icon |
| [`Celesteos-agent-windows`](https://github.com/shortalex12333/Celesteos-agent-windows) | Windows agent — EXE installer via GitHub Actions |
| [`celesteos-portal`](https://github.com/shortalex12333/celesteos-portal) | Download portal frontend (Vercel → registration.celeste7.ai) |
| [`Cloud_PMS`](https://github.com/shortalex12333/Cloud_PMS) | Main yacht management system (search, lenses, actions) |

## Supabase Storage Layout

```
installers/
  dmg/
    MY_FREEDOM/
      CelesteOS-MY_FREEDOM.dmg              (38.9 MB)
    TEST_YACHT_004/
      CelesteOS-TEST_YACHT_004.dmg          (33.2 MB)
    TEST_YACHT_006/
      CelesteOS-TEST_YACHT_006.dmg          (33.2 MB)
  exe/
    73b36cab-.../
      CelesteOS-Setup-73b36cab-...exe       (Windows)
```
