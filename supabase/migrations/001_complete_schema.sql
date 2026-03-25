-- CelesteOS Cloud Schema
-- ======================
-- Complete database schema for secure DMG distribution and agent authentication.
--
-- Security Model:
-- - yacht_id: Public identifier (embedded in DMG, immutable)
-- - yacht_id_hash: SHA256(yacht_id) for identity verification
-- - shared_secret: 256-bit random, retrieved ONE TIME, stored in Keychain
-- - All API requests authenticated with HMAC-SHA256(payload, shared_secret)

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- FLEET REGISTRY
-- ============================================================================
CREATE TABLE IF NOT EXISTS fleet_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    yacht_id TEXT UNIQUE NOT NULL,
    yacht_id_hash TEXT UNIQUE NOT NULL,
    yacht_name TEXT NOT NULL,
    yacht_model TEXT,
    buyer_email TEXT NOT NULL,
    buyer_name TEXT,
    user_id UUID,
    shared_secret TEXT,
    active BOOLEAN DEFAULT FALSE,
    credentials_retrieved BOOLEAN DEFAULT FALSE,
    credentials_retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    registered_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    registration_ip TEXT,
    activation_ip TEXT,
    last_seen_at TIMESTAMPTZ,
    api_calls_count INTEGER DEFAULT 0,
    CONSTRAINT yacht_id_format CHECK (yacht_id ~ '^[A-Z0-9_-]+$')
);

CREATE INDEX IF NOT EXISTS idx_fleet_registry_active ON fleet_registry(active);
CREATE INDEX IF NOT EXISTS idx_fleet_registry_buyer_email ON fleet_registry(buyer_email);
CREATE INDEX IF NOT EXISTS idx_fleet_registry_yacht_id_hash ON fleet_registry(yacht_id_hash);

-- ============================================================================
-- DOWNLOAD LINKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS download_links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    yacht_id TEXT NOT NULL REFERENCES fleet_registry(yacht_id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    download_count INTEGER DEFAULT 0,
    max_downloads INTEGER DEFAULT 3,
    last_download_at TIMESTAMPTZ,
    last_download_ip TEXT,
    expires_at TIMESTAMPTZ NOT NULL,
    is_activation_link BOOLEAN DEFAULT FALSE,
    used BOOLEAN DEFAULT FALSE,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_download_links_yacht_id ON download_links(yacht_id);
CREATE INDEX IF NOT EXISTS idx_download_links_token_hash ON download_links(token_hash);

-- ============================================================================
-- AUDIT LOG
-- ============================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    yacht_id TEXT REFERENCES fleet_registry(yacht_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_yacht_id ON audit_log(yacht_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at DESC);

-- ============================================================================
-- SECURITY EVENTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    yacht_id TEXT REFERENCES fleet_registry(yacht_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    details JSONB DEFAULT '{}',
    ip_address TEXT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_events_yacht_id ON security_events(yacht_id);
CREATE INDEX IF NOT EXISTS idx_security_events_severity ON security_events(severity);
CREATE INDEX IF NOT EXISTS idx_security_events_created_at ON security_events(created_at DESC);

-- ============================================================================
-- FUNCTIONS
-- ============================================================================

-- Generate shared secret
CREATE OR REPLACE FUNCTION generate_shared_secret()
RETURNS TEXT AS $$
BEGIN
    RETURN encode(gen_random_bytes(32), 'hex');
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Activate yacht
CREATE OR REPLACE FUNCTION activate_yacht(p_yacht_id TEXT, p_shared_secret TEXT DEFAULT NULL)
RETURNS TABLE(success BOOLEAN, message TEXT) AS $$
DECLARE
    v_secret TEXT;
    v_is_active BOOLEAN;
BEGIN
    SELECT active INTO v_is_active FROM fleet_registry WHERE yacht_id = p_yacht_id;
    IF NOT FOUND THEN RETURN QUERY SELECT FALSE, 'Yacht not found'::TEXT; RETURN; END IF;
    IF v_is_active THEN
        RETURN QUERY SELECT TRUE, 'Already activated'::TEXT; RETURN;
    END IF;
    v_secret := COALESCE(p_shared_secret, generate_shared_secret());
    UPDATE fleet_registry SET shared_secret = v_secret, active = TRUE, activated_at = NOW()
    WHERE yacht_id = p_yacht_id;
    RETURN QUERY SELECT TRUE, 'Activation successful'::TEXT;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Retrieve credentials (ONE TIME ONLY)
CREATE OR REPLACE FUNCTION retrieve_credentials(p_yacht_id TEXT)
RETURNS TABLE(status TEXT, shared_secret TEXT, retrieved_at TIMESTAMPTZ) AS $$
DECLARE
    v_yacht RECORD;
BEGIN
    SELECT fr.* INTO v_yacht FROM fleet_registry fr WHERE fr.yacht_id = p_yacht_id FOR UPDATE;
    IF NOT FOUND THEN RETURN QUERY SELECT 'not_found'::TEXT, NULL::TEXT, NULL::TIMESTAMPTZ; RETURN; END IF;
    IF NOT v_yacht.active THEN
        RETURN QUERY SELECT 'not_activated'::TEXT, NULL::TEXT, NULL::TIMESTAMPTZ; RETURN;
    END IF;
    IF v_yacht.credentials_retrieved THEN
        RETURN QUERY SELECT 'already_retrieved'::TEXT, NULL::TEXT, v_yacht.credentials_retrieved_at; RETURN;
    END IF;
    UPDATE fleet_registry SET credentials_retrieved = TRUE, credentials_retrieved_at = NOW()
    WHERE yacht_id = p_yacht_id;
    RETURN QUERY SELECT 'success'::TEXT, v_yacht.shared_secret, NOW()::TIMESTAMPTZ;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Verify yacht hash
CREATE OR REPLACE FUNCTION verify_yacht_hash(p_yacht_id TEXT, p_hash TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN encode(digest(p_yacht_id, 'sha256'), 'hex') = lower(p_hash);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ============================================================================
-- ROW LEVEL SECURITY
-- ============================================================================
ALTER TABLE fleet_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE download_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON fleet_registry FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON download_links FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON audit_log FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role full access" ON security_events FOR ALL USING (auth.role() = 'service_role');

-- ============================================================================
-- TRIGGERS
-- ============================================================================
-- No triggers needed for current schema
