-- ============================================================
-- ADD TENANT CREDENTIALS TO FLEET REGISTRY
-- ============================================================
-- The verify-2fa endpoint returns these to the agent so it can
-- connect to the yacht's tenant Supabase instance.
-- Without these columns, the agent gets empty strings and can't sync.
-- ============================================================

ALTER TABLE fleet_registry
  ADD COLUMN IF NOT EXISTS tenant_supabase_url TEXT,
  ADD COLUMN IF NOT EXISTS tenant_supabase_service_key TEXT;

COMMENT ON COLUMN fleet_registry.tenant_supabase_url IS 'Tenant Supabase URL returned to agent at activation';
COMMENT ON COLUMN fleet_registry.tenant_supabase_service_key IS 'Tenant service-role key returned to agent at activation (one-time)';
