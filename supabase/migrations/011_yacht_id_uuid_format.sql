-- ============================================================
-- FIX: yacht_id must be UUID, not uppercase slug
-- ============================================================
-- The CHECK constraint forced uppercase slugs (MY_FREEDOM).
-- yacht_id should always be a system-generated UUID for security
-- (unpredictable, no enumeration). Drop the constraint.
-- ============================================================

ALTER TABLE fleet_registry DROP CONSTRAINT IF EXISTS yacht_id_format;
