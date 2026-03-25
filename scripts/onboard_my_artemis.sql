-- ============================================================
-- ONBOARD: M/Y Artemis (TEST YACHT)
-- ============================================================
-- Run in Supabase SQL Editor on MASTER project.
--
-- Pre-requisites:
--   1. Run migrations 010 + 011 first
--   2. Tenant Supabase project exists
-- ============================================================

DO $$
DECLARE
    v_yacht_id TEXT := gen_random_uuid()::text;
BEGIN
    INSERT INTO fleet_registry (
        yacht_id,
        yacht_id_hash,
        yacht_name,
        yacht_model,
        buyer_name,
        buyer_email,
        tenant_supabase_url,
        tenant_supabase_service_key
    ) VALUES (
        v_yacht_id,
        encode(digest(v_yacht_id, 'sha256'), 'hex'),
        'M/Y Artemis',
        'Sunseeker 76',
        'James Whitmore',
        'x@alex-short.com',
        'https://vzsohavtuotocgrfkfyd.supabase.co',
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6c29oYXZ0dW90b2NncmZrZnlkIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MzU5Mjg3NSwiZXhwIjoyMDc5MTY4ODc1fQ.fC7eC_4xGnCHIebPzfaJ18pFMPKgImE7BuN0I3A-pSY'
    );

    RAISE NOTICE '====================================';
    RAISE NOTICE 'yacht_id: %', v_yacht_id;
    RAISE NOTICE 'yacht_id_hash: %', encode(digest(v_yacht_id, 'sha256'), 'hex');
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Write these to ~/.celesteos/install_manifest.json';
END $$;

-- Copy yacht_id and hash from the output above
SELECT yacht_id, yacht_id_hash, yacht_name, buyer_email, active
FROM fleet_registry
WHERE yacht_name = 'M/Y Artemis'
ORDER BY created_at DESC
LIMIT 1;
