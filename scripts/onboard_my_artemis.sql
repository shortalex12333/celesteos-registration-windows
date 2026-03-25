-- ============================================================
-- ONBOARD: M/Y Artemis (TEST YACHT)
-- ============================================================
-- Run in Supabase SQL Editor on MASTER project.
--
-- Pre-requisites:
--   1. Run migrations 010 + 011 + 012 first
--   2. Tenant Supabase project exists
--
-- NOTE: This uses a FIXED yacht_id so it can be re-run without
-- creating duplicates. If the row already exists, it updates it.
-- ============================================================

INSERT INTO fleet_registry (
    yacht_id,
    yacht_id_hash,
    yacht_name,
    yacht_model,
    buyer_name,
    buyer_email,
    tenant_supabase_url,
    tenant_supabase_service_key,
    installer_type
) VALUES (
    '73b36cab-a606-4b85-ab64-a11aae62d966',
    encode(digest('73b36cab-a606-4b85-ab64-a11aae62d966', 'sha256'), 'hex'),
    'M/Y Artemis',
    'Sunseeker 76',
    'James Whitmore',
    'x@alex-short.com',
    'https://vzsohavtuotocgrfkfyd.supabase.co',
    'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6c29oYXZ0dW90b2NncmZrZnlkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MzU5Mjg3NSwiZXhwIjoyMDc5MTY4ODc1fQ.fC7eC_4xGnCHIebPzfaJ18pFMPKgImE7BuN0I3A-pSY',
    'dmg'  -- 'dmg' for macOS, 'exe' for Windows
)
ON CONFLICT (yacht_id) DO UPDATE SET
    yacht_name = EXCLUDED.yacht_name,
    yacht_model = EXCLUDED.yacht_model,
    buyer_name = EXCLUDED.buyer_name,
    buyer_email = EXCLUDED.buyer_email,
    tenant_supabase_url = EXCLUDED.tenant_supabase_url,
    tenant_supabase_service_key = EXCLUDED.tenant_supabase_service_key,
    installer_type = EXCLUDED.installer_type;

-- Verify
SELECT yacht_id, yacht_id_hash, yacht_name, buyer_email, installer_type, active
FROM fleet_registry
WHERE yacht_id = '73b36cab-a606-4b85-ab64-a11aae62d966';

-- Config paths for the agent:
--   macOS:   ~/.celesteos/install_manifest.json
--   Windows: %APPDATA%\CelesteOS\install_manifest.json
