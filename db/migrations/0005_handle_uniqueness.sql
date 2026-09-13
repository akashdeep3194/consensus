-- ═══════════════════════════════════════════════════════════════════════════
-- Case-insensitive handle uniqueness.
--
-- The leaderboard and every result board display a handle as if it
-- identifies exactly one player. Without this, a second account whose
-- provider-supplied display name collides with an existing handle (case
-- aside) could show up as that player everywhere the game publishes a name.
--
-- Provisioning (adapters.*.user_repository.ensure_user) already avoids new
-- collisions by trying a suffixed variant; this index is the backstop that
-- makes a collision impossible even under a race, and the reason a repeat
-- login can trust its own handle was never silently taken by someone else.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

DROP INDEX IF EXISTS users_handle_idx;
CREATE UNIQUE INDEX users_handle_unique_idx ON users (lower(handle)) WHERE handle IS NOT NULL;

COMMIT;
