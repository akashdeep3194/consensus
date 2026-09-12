-- Migration bookkeeping. Must be the first migration applied.
-- Numbered SQL files plus a ledger: enough discipline to know what has run,
-- without taking a dependency on a migration framework this early.
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename    text PRIMARY KEY,
  checksum    text NOT NULL,
  applied_at  timestamptz NOT NULL DEFAULT now()
);
