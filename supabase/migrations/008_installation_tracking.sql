-- Installation session tracking, installation step logs, 2FA codes

CREATE TABLE IF NOT EXISTS installation_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    yacht_id TEXT NOT NULL REFERENCES fleet_registry(yacht_id),
    session_token TEXT UNIQUE NOT NULL,
    state TEXT NOT NULL DEFAULT 'started'
        CHECK (state IN ('started','registered','pending_activation',
                         'activated','folder_assigned','operational','failed')),
    installer_version TEXT,
    os_version TEXT,
    mac_hostname TEXT,
    mac_serial_hash TEXT,
    nas_root TEXT,
    source_type TEXT CHECK (source_type IN ('nas','onedrive','local')),
    ip_address TEXT,
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS installation_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES installation_sessions(id),
    yacht_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success','failed','skipped')),
    details JSONB DEFAULT '{}',
    duration_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS twofa_codes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    yacht_id TEXT NOT NULL REFERENCES fleet_registry(yacht_id),
    code_hash TEXT NOT NULL,
    purpose TEXT DEFAULT 'installation',
    email_sent_to TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMPTZ,
    attempts INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_install_sessions_yacht ON installation_sessions(yacht_id);
CREATE INDEX IF NOT EXISTS idx_install_sessions_state ON installation_sessions(state) WHERE state != 'operational';
CREATE INDEX IF NOT EXISTS idx_install_logs_session ON installation_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_twofa_yacht ON twofa_codes(yacht_id);
CREATE INDEX IF NOT EXISTS idx_twofa_expires ON twofa_codes(expires_at) WHERE verified = FALSE;

-- RLS (service_role only)
ALTER TABLE installation_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE installation_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE twofa_codes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "svc_install_sessions" ON installation_sessions
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "svc_install_logs" ON installation_logs
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "svc_twofa_codes" ON twofa_codes
    FOR ALL USING (auth.role() = 'service_role');
