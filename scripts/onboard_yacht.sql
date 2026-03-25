-- ============================================================
-- ONBOARD NEW YACHT
-- ============================================================
-- Run this in Supabase SQL Editor (master project) after
-- receiving payment. Only edit the marked values.
--
-- yacht_id is auto-generated as a random UUID — never manual.
-- yacht_id_hash is auto-computed from yacht_id.
--
-- After running:
--   1. Copy the yacht_id from the output
--   2. Run build_dmg.py (macOS) or build_exe.py (Windows) with that yacht_id
--   3. Installer uploads automatically to Storage
--   4. Buyer downloads from download.celeste7.ai
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
        tenant_supabase_service_key,
        installer_type
    ) VALUES (
        v_yacht_id,
        encode(digest(v_yacht_id, 'sha256'), 'hex'),
        -- ⬇️ EDIT THESE VALUES ⬇️
        'M/Y New Yacht',                    -- yacht_name (display name)
        'Sunseeker 76',                      -- yacht_model (optional)
        'Buyer Company Ltd',                 -- buyer_name
        'captain@theiryacht.com',            -- buyer_email (where 2FA goes)
        'https://TENANT.supabase.co',        -- tenant_supabase_url
        'eyJ...',                            -- tenant_supabase_service_key
        'dmg'                                -- installer_type: 'dmg' (macOS) or 'exe' (Windows)
        -- ⬆️ EDIT THESE VALUES ⬆️
    );

    RAISE NOTICE '====================================';
    RAISE NOTICE 'YACHT ONBOARDED';
    RAISE NOTICE 'yacht_id: %', v_yacht_id;
    RAISE NOTICE 'yacht_id_hash: %', encode(digest(v_yacht_id, 'sha256'), 'hex');
    RAISE NOTICE '====================================';
    RAISE NOTICE 'Next: run build_dmg.py (macOS) or build_exe.py (Windows) with yacht_id: %', v_yacht_id;
END $$;

-- Verify (edit yacht_name to match):
SELECT yacht_id, yacht_id_hash, yacht_name, buyer_email, active, created_at
FROM fleet_registry
ORDER BY created_at DESC
LIMIT 1;
