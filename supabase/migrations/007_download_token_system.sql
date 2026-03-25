-- Download Token Generation System
-- ==================================
-- Separate system for DMG download tokens vs activation tokens
--
-- Flow:
-- 1. DMG built and uploaded to storage
-- 2. Admin generates download token
-- 3. Buyer receives email with download link
-- 4. Buyer uses token to download DMG
-- 5. After install, separate activation token system takes over

CREATE OR REPLACE FUNCTION generate_download_token(
    p_yacht_id TEXT,
    p_expires_days INTEGER DEFAULT 7,
    p_max_downloads INTEGER DEFAULT 3
)
RETURNS TABLE(
    token TEXT,
    token_hash TEXT,
    download_link TEXT,
    expires_at TIMESTAMPTZ
) AS $$
DECLARE
    v_token TEXT;
    v_token_hash TEXT;
    v_expires_at TIMESTAMPTZ;
    v_link_id UUID;
    v_base_url TEXT := 'https://qvzmkaamzaqxpzbewjxe.supabase.co/functions/v1/download';
BEGIN
    -- Verify yacht exists
    IF NOT EXISTS (SELECT 1 FROM fleet_registry WHERE yacht_id = p_yacht_id) THEN
        RAISE EXCEPTION 'Yacht % not found', p_yacht_id;
    END IF;

    -- Generate cryptographically secure token
    v_token := encode(gen_random_bytes(32), 'hex');
    v_token_hash := encode(digest(v_token, 'sha256'), 'hex');
    v_expires_at := NOW() + (p_expires_days || ' days')::INTERVAL;

    -- Insert into download_links table
    INSERT INTO download_links (
        yacht_id,
        token_hash,
        is_activation_link,
        expires_at,
        download_count,
        max_downloads,
        created_at
    ) VALUES (
        p_yacht_id,
        v_token_hash,
        FALSE,  -- This is a download token, not activation
        v_expires_at,
        0,
        p_max_downloads,
        NOW()
    ) RETURNING id INTO v_link_id;

    -- Return token and download link
    RETURN QUERY SELECT
        v_token,
        v_token_hash,
        v_base_url || '?token=' || v_token AS download_link,
        v_expires_at;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION generate_download_token IS 'Generate secure download token for DMG distribution';


-- Function to validate download token (separate from activation)
CREATE OR REPLACE FUNCTION validate_download_token(
    p_token TEXT
)
RETURNS TABLE(
    valid BOOLEAN,
    message TEXT,
    yacht_id TEXT,
    download_count INTEGER,
    max_downloads INTEGER
) AS $$
DECLARE
    v_token_hash TEXT;
    v_link RECORD;
BEGIN
    -- Hash the provided token
    v_token_hash := encode(digest(p_token, 'sha256'), 'hex');

    -- Find matching download link
    SELECT * INTO v_link
    FROM download_links
    WHERE token_hash = v_token_hash
      AND is_activation_link = FALSE;  -- Only download tokens

    -- No token found
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Invalid download token'::TEXT, NULL::TEXT, NULL::INTEGER, NULL::INTEGER;
        RETURN;
    END IF;

    -- Check if expired
    IF v_link.expires_at <= NOW() THEN
        RETURN QUERY SELECT FALSE, 'Download link expired'::TEXT, v_link.yacht_id, v_link.download_count, v_link.max_downloads;
        RETURN;
    END IF;

    -- Check download limit
    IF v_link.download_count >= v_link.max_downloads THEN
        RETURN QUERY SELECT FALSE, 'Maximum downloads reached'::TEXT, v_link.yacht_id, v_link.download_count, v_link.max_downloads;
        RETURN;
    END IF;

    -- Token is valid
    RETURN QUERY SELECT TRUE, 'Valid'::TEXT, v_link.yacht_id, v_link.download_count, v_link.max_downloads;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION validate_download_token IS 'Validate download token and check limits';


-- Function to increment download count
CREATE OR REPLACE FUNCTION increment_download_count(
    p_token TEXT,
    p_ip_address TEXT DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_token_hash TEXT;
BEGIN
    v_token_hash := encode(digest(p_token, 'sha256'), 'hex');

    UPDATE download_links
    SET download_count = download_count + 1,
        last_download_at = NOW(),
        last_download_ip = COALESCE(p_ip_address, last_download_ip)
    WHERE token_hash = v_token_hash
      AND is_activation_link = FALSE;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION increment_download_count IS 'Increment download counter after successful download';
