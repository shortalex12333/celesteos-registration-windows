-- =============================================================================
-- Migration 014: user_accounts table (crew identity directory)
-- =============================================================================
--
-- Architecture note (2026-04-09):
-- This table lives on the MASTER Supabase project (qvzmkaamzaqxpzbewjxe).
-- It is the bridge between auth.users (Supabase auth) and the tenant DB
-- (vzsohavtuotocgrfkfyd, operational data).
--
-- Read path (apps/api/middleware/auth.py — lookup_tenant_for_user):
--   1. Decode JWT (signed by MASTER)
--   2. Look up user_accounts by id → get yacht_id + status
--   3. Look up fleet_registry by yacht_id → get tenant_key_alias
--   4. Query tenant auth_users_roles by user_id + yacht_id → get role
--   5. Cache result for 15 min (TTLCache)
--
-- Write path (celesteos-registration-windows — /api/invite-users):
--   After generate_link returns the new user UUID, write this row
--   immediately so the user is admissible from the moment they click
--   the magic link (before they have ever logged in).
--
-- Fleet access:
--   fleet_vessel_ids is NULL for single-vessel crew.
--   For fleet managers/owners, populate with array of yacht_ids.
--   auth.py gates fleet view on BOTH fleet_vessel_ids AND role ∈ {manager, owner}.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.user_accounts (
    -- Identity (FK to Supabase auth.users — same UUID)
    id                    UUID PRIMARY KEY,

    -- Vessel assignment
    yacht_id              TEXT        NOT NULL REFERENCES fleet_registry(yacht_id) ON DELETE RESTRICT,

    -- Contact
    email                 TEXT        NOT NULL,
    display_name          TEXT,

    -- Account state
    status                TEXT        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'suspended', 'pending')),
    email_verified        BOOLEAN     NOT NULL DEFAULT FALSE,

    -- Role (denormalised for fast lookup; authoritative role is in tenant auth_users_roles)
    role                  TEXT        CHECK (role IN (
                              'captain', 'deck', 'chief_engineer', 'eto',
                              'interior', 'crew', 'manager', 'vendor', 'owner'
                          )),

    -- Fleet access (NULL = single-vessel; populated for manager/owner fleet users)
    fleet_vessel_ids      TEXT[],

    -- Login tracking
    last_login            TIMESTAMPTZ,
    login_count           INTEGER     NOT NULL DEFAULT 0,
    failed_login_attempts INTEGER     NOT NULL DEFAULT 0,
    locked_until          TIMESTAMPTZ,

    -- Timestamps
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index: tenant lookup (most common read pattern in auth.py)
CREATE INDEX IF NOT EXISTS idx_user_accounts_yacht_id
    ON public.user_accounts(yacht_id);

-- Index: email lookup (re-invite deduplication, admin queries)
CREATE INDEX IF NOT EXISTS idx_user_accounts_email
    ON public.user_accounts(email);

-- Index: fleet vessel lookup (fleet manager queries)
CREATE INDEX IF NOT EXISTS idx_user_accounts_fleet_vessel_ids
    ON public.user_accounts USING GIN(fleet_vessel_ids);

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_user_accounts_updated_at
    BEFORE UPDATE ON public.user_accounts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS: users can read their own row; service role has full access
ALTER TABLE public.user_accounts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own account"
    ON public.user_accounts
    FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Service role has full access"
    ON public.user_accounts
    FOR ALL
    USING (auth.role() = 'service_role');
