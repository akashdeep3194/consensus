-- ═══════════════════════════════════════════════════════════════════════════
-- User profile fields: display handle and email for OAuth identities.
-- Allows external_id to remain the provider's stable subject (e.g. Google sub)
-- while presenting a human-readable handle on the leaderboard and results.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

ALTER TABLE users ADD COLUMN IF NOT EXISTS handle text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;

-- For existing dev rows, external_id is already the handle.
UPDATE users SET handle = external_id WHERE handle IS NULL;

-- Index handle lookups
CREATE INDEX IF NOT EXISTS users_handle_idx ON users (handle) WHERE handle IS NOT NULL;

COMMIT;
