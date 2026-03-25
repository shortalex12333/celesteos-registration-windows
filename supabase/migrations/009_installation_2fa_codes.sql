-- Installation-specific 2FA codes
-- Separate from user account twofa_codes (which uses user_id UUID FK)
-- This table is keyed on yacht_id for the installation/download flow

CREATE TABLE IF NOT EXISTS installation_2fa_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    yacht_id TEXT NOT NULL REFERENCES fleet_registry(yacht_id),
    code_hash TEXT NOT NULL,
    purpose TEXT DEFAULT 'installation'
        CHECK (purpose IN ('installation', 'download')),
    email_sent_to TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inst_2fa_yacht ON installation_2fa_codes(yacht_id);
CREATE INDEX IF NOT EXISTS idx_inst_2fa_expires ON installation_2fa_codes(expires_at) WHERE verified = FALSE;

ALTER TABLE installation_2fa_codes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "svc_inst_2fa" ON installation_2fa_codes
    FOR ALL USING (auth.role() = 'service_role');
