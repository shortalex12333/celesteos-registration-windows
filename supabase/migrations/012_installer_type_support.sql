-- Installer Type + Platform Support
-- ==================================
-- Adds platform awareness to the download flow so Windows yachts
-- receive an .exe installer instead of a macOS .dmg.
--
-- Also backfills missing columns that the registration API uses
-- but were added via dashboard, not migrations.

-- ============================================================
-- fleet_registry: installer type
-- ============================================================
ALTER TABLE fleet_registry
  ADD COLUMN IF NOT EXISTS installer_type TEXT NOT NULL DEFAULT 'dmg'
    CHECK (installer_type IN ('dmg', 'exe'));

COMMENT ON COLUMN fleet_registry.installer_type IS 'Installer format: dmg (macOS) or exe (Windows)';

-- ============================================================
-- download_links: missing columns used by registration API
-- ============================================================

-- Raw download token (stored alongside its hash for token-based lookups)
ALTER TABLE download_links
  ADD COLUMN IF NOT EXISTS download_token TEXT;

-- Internal reference code (not user-facing)
ALTER TABLE download_links
  ADD COLUMN IF NOT EXISTS twofa_code TEXT;

-- Resolved storage path for the installer file
ALTER TABLE download_links
  ADD COLUMN IF NOT EXISTS package_path TEXT;

COMMENT ON COLUMN download_links.package_path IS 'Supabase Storage path to the installer file';

-- Alias for download timestamp (API uses last_downloaded_at, schema had last_download_at)
ALTER TABLE download_links
  ADD COLUMN IF NOT EXISTS last_downloaded_at TIMESTAMPTZ;

-- Target platform for this download link
ALTER TABLE download_links
  ADD COLUMN IF NOT EXISTS platform TEXT NOT NULL DEFAULT 'macos'
    CHECK (platform IN ('macos', 'windows'));

COMMENT ON COLUMN download_links.platform IS 'Target platform for this download link';
