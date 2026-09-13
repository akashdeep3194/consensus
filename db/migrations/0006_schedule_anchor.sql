-- ═══════════════════════════════════════════════════════════════════════════
-- Self-persisting round anchor.
--
-- api/deps.py::_anchor() used to recompute "midnight UTC today" on every
-- process restart whenever ROUND_ANCHOR was unset — which was always true in
-- production (render.yaml never set it). Cycle numbers are counted forward
-- from the anchor, so a restart landing on a different calendar day silently
-- reused an earlier cycle number instead of minting a new one, and the only
-- live round got fast-forwarded to REVEALED with nothing behind it.
--
-- A singleton row removes the operator-memory dependency entirely: the
-- anchor is decided once, by whichever process boots first against a given
-- database, and every later boot reads the same value back instead of
-- recomputing it from wall-clock time. services/anchor.py.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

CREATE TABLE schedule_anchor (
  id      boolean PRIMARY KEY DEFAULT true,
  anchor  timestamptz NOT NULL,
  CONSTRAINT schedule_anchor_is_singleton CHECK (id)
);

COMMENT ON TABLE schedule_anchor IS
  'Exactly one row (boolean PK + CHECK(id) make a second impossible): cycle '
  '0''s opening instant, chosen once and never recomputed. services/anchor.py.';

COMMIT;
