-- ═══════════════════════════════════════════════════════════════════════════
-- Drafts and submissions.
--
-- Every structural invariant the engine raises InvalidSubmissionSet for is
-- ALSO a database constraint here. The engine protects the resolver; these
-- protect the data, and they hold even when the application is wrong.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- ── drafts: mutable, durable, excluded from the tally ──────────────────────
-- Columns are nullable because a player legitimately fills one field first.
-- "Valid" is defined once, as a generated column, so the seal query and the
-- API agree by construction rather than by convention (F6).

CREATE TABLE round_drafts (
  round_id   uuid NOT NULL REFERENCES rounds ON DELETE CASCADE,
  user_id    uuid NOT NULL REFERENCES users  ON DELETE CASCADE,
  prediction prediction_slate,
  vote       vote_digit,
  version    bigint NOT NULL DEFAULT 1,        -- optimistic concurrency (§5.2)
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),

  is_complete boolean NOT NULL
    GENERATED ALWAYS AS (prediction IS NOT NULL AND vote IS NOT NULL) STORED,

  PRIMARY KEY (round_id, user_id),
  CONSTRAINT version_advances CHECK (version >= 1)
);

COMMENT ON COLUMN round_drafts.is_complete IS
  'Ruleset V1.1 §4: a draft auto-commits at seal only if complete. Generated so '
  'the definition cannot drift between the sealing worker and the API.';

-- the sealing worker scans exactly this
CREATE INDEX drafts_sealable_idx ON round_drafts (round_id) WHERE is_complete;

CREATE FUNCTION touch_draft() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER drafts_touch BEFORE UPDATE ON round_drafts
  FOR EACH ROW EXECUTE FUNCTION touch_draft();

-- ── submissions: immutable, the authoritative input set ────────────────────

CREATE TYPE submission_source AS ENUM ('manual', 'auto_seal');

CREATE TABLE submissions (
  submission_id    uuid PRIMARY KEY,
  round_id         uuid NOT NULL REFERENCES rounds ON DELETE RESTRICT,
  user_id          uuid NOT NULL REFERENCES users  ON DELETE RESTRICT,
  prediction       prediction_slate NOT NULL,
  vote             vote_digit NOT NULL,
  commit_sequence  bigint NOT NULL,
  committed_at     timestamptz NOT NULL DEFAULT now(),
  source           submission_source NOT NULL,
  mandate_eligible boolean NOT NULL,
  idempotency_key  text,
  voided_at        timestamptz,                -- anti-abuse; never deletes rows
  void_reason      text,

  -- one entry per account per round (§4, and engine InvalidSubmissionSet)
  CONSTRAINT one_entry_per_user UNIQUE (round_id, user_id),
  -- commit_sequence must be unique per round or the Merkle leaf order is
  -- ambiguous and the root stops being reproducible (F4)
  CONSTRAINT commit_sequence_unique UNIQUE (round_id, commit_sequence),
  CONSTRAINT commit_sequence_positive CHECK (commit_sequence > 0),
  CONSTRAINT void_reason_with_void CHECK (
    (voided_at IS NULL) = (void_reason IS NULL)
  )
);

-- retries must be safe (§6.3): the same key can never create a second row
CREATE UNIQUE INDEX submissions_idempotency_idx
  ON submissions (round_id, user_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

-- resolution reads the round's set in commit order
CREATE INDEX submissions_round_seq_idx ON submissions (round_id, commit_sequence);
-- Board B reads only eligible, non-voided rows
CREATE INDEX submissions_mandate_idx ON submissions (round_id)
  WHERE mandate_eligible AND voided_at IS NULL;
-- a player's history
CREATE INDEX submissions_user_idx ON submissions (user_id, committed_at DESC);

-- ── immutability, enforced rather than promised ────────────────────────────
-- §1.3: "A committed entry can never be edited, withdrawn, or replaced."
-- Voiding is the ONLY permitted mutation, and it never alters the entry's
-- content — so the resolver stays a pure function of immutable data (F9).

CREATE FUNCTION submissions_are_immutable() RETURNS trigger AS $$
BEGIN
  IF (NEW.submission_id, NEW.round_id, NEW.user_id, NEW.prediction,
      NEW.vote, NEW.commit_sequence, NEW.committed_at, NEW.source,
      NEW.mandate_eligible)
     IS DISTINCT FROM
     (OLD.submission_id, OLD.round_id, OLD.user_id, OLD.prediction,
      OLD.vote, OLD.commit_sequence, OLD.committed_at, OLD.source,
      OLD.mandate_eligible)
  THEN
    RAISE EXCEPTION 'submission % is immutable; only voiding is permitted',
      OLD.submission_id USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER submissions_immutable BEFORE UPDATE ON submissions
  FOR EACH ROW EXECUTE FUNCTION submissions_are_immutable();

CREATE FUNCTION submissions_no_delete() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'submissions are append-only; void instead of deleting'
    USING ERRCODE = 'check_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER submissions_append_only BEFORE DELETE ON submissions
  FOR EACH ROW EXECUTE FUNCTION submissions_no_delete();

-- ── no writes once the round stops accepting them ──────────────────────────
-- §6.2: a post-seal mutation must be rejected through ANY path.

CREATE FUNCTION reject_write_to_closed_round() RETURNS trigger AS $$
DECLARE
  current_status round_status;
  target_round   uuid := COALESCE(NEW.round_id, OLD.round_id);
BEGIN
  SELECT status INTO current_status FROM rounds WHERE round_id = target_round;
  IF current_status IS NULL THEN
    RAISE EXCEPTION 'round % does not exist', target_round USING ERRCODE = 'foreign_key_violation';
  END IF;
  IF current_status NOT IN ('open', 'blackout', 'sealing') THEN
    RAISE EXCEPTION 'round % is %; it no longer accepts entries',
      target_round, current_status USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER drafts_round_must_be_accepting
  BEFORE INSERT OR UPDATE ON round_drafts
  FOR EACH ROW EXECUTE FUNCTION reject_write_to_closed_round();

CREATE TRIGGER submissions_round_must_be_accepting
  BEFORE INSERT ON submissions
  FOR EACH ROW EXECUTE FUNCTION reject_write_to_closed_round();

COMMIT;
