-- ═══════════════════════════════════════════════════════════════════════════
-- Project Consensus 3D — initial schema
-- Ruleset V1.1 (docs/00-ruleset.md).
--
-- PostgreSQL is authoritative for every piece of state that can affect an
-- outcome. Rules that the engine enforces in memory are enforced AGAIN here,
-- because the database is the last line of defence and the only one that holds
-- when application code is wrong.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

-- ── domains: one definition of a value, reused everywhere ──────────────────
-- Defining these as DOMAINs rather than repeating CHECK clauses per column
-- means the rule for "what is a valid slate" lives in exactly one place.

CREATE DOMAIN prediction_slate AS char(3)
  CONSTRAINT three_digits CHECK (VALUE ~ '^[0-9]{3}$')
  CONSTRAINT digits_distinct CHECK (
        substr(VALUE, 1, 1) <> substr(VALUE, 2, 1)
    AND substr(VALUE, 2, 1) <> substr(VALUE, 3, 1)
    AND substr(VALUE, 1, 1) <> substr(VALUE, 3, 1)
  );
COMMENT ON DOMAIN prediction_slate IS
  'Three distinct digits, ordered. 720 valid values. Ruleset V1.1 §1.';

CREATE DOMAIN vote_digit AS smallint
  CONSTRAINT single_digit CHECK (VALUE BETWEEN 0 AND 9);

CREATE DOMAIN merkle_root AS char(64)
  CONSTRAINT lowercase_hex CHECK (VALUE ~ '^[0-9a-f]{64}$');

-- ── round lifecycle ────────────────────────────────────────────────────────

CREATE TYPE round_status AS ENUM (
  'scheduled', 'open', 'blackout', 'sealing', 'sealed', 'resolving', 'revealed', 'voided'
);

-- Legal transitions live as DATA, not as branching logic: adding a phase is an
-- INSERT, not a code change. The trigger below is closed for modification.
CREATE TABLE round_transitions (
  from_status round_status NOT NULL,
  to_status   round_status NOT NULL,
  PRIMARY KEY (from_status, to_status)
);

INSERT INTO round_transitions (from_status, to_status) VALUES
  ('scheduled', 'open'),
  ('open',      'blackout'),
  ('blackout',  'sealing'),
  ('sealing',   'sealed'),
  ('sealed',    'resolving'),
  ('resolving', 'revealed'),
  -- a round may be abandoned from any pre-reveal state
  ('scheduled', 'voided'), ('open', 'voided'), ('blackout', 'voided'),
  ('sealing',   'voided'), ('sealed', 'voided'), ('resolving', 'voided');

CREATE TABLE users (
  user_id     uuid PRIMARY KEY,
  external_id text NOT NULL,                    -- provider subject (OAuth)
  provider    text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  disabled_at timestamptz,
  UNIQUE (provider, external_id)
);

CREATE TABLE rounds (
  round_id          uuid PRIMARY KEY,
  cycle_number      bigint NOT NULL UNIQUE,
  status            round_status NOT NULL DEFAULT 'scheduled',

  -- Canonical boundaries. Client clocks never determine eligibility (§6.4).
  opens_at          timestamptz NOT NULL,
  mandate_deadline  timestamptz NOT NULL,       -- T+12h, Board B eligibility (§3.2)
  blackout_at       timestamptz NOT NULL,       -- T+23h
  seals_at          timestamptz NOT NULL,       -- T+24h
  reveals_at        timestamptz NOT NULL,       -- T+30h

  ruleset_version   text NOT NULL,
  algorithm_version text NOT NULL,

  -- populated during sealing / resolution, never before
  commitment_root   merkle_root,
  committed_at_seal timestamptz,
  winning_number    prediction_slate,
  resolved_at       timestamptz,
  revealed_at       timestamptz,

  CONSTRAINT phases_strictly_ordered CHECK (
    opens_at < mandate_deadline
      AND mandate_deadline < blackout_at
      AND blackout_at < seals_at
      AND seals_at < reveals_at
  ),
  -- A root may only exist once the input set is immutable.
  CONSTRAINT root_requires_sealed CHECK (
    commitment_root IS NULL OR status IN ('sealed', 'resolving', 'revealed', 'voided')
  ),
  -- The winning number may only exist after resolution.
  CONSTRAINT winner_requires_resolved CHECK (
    winning_number IS NULL OR status IN ('resolving', 'revealed', 'voided')
  )
);

CREATE INDEX rounds_status_idx   ON rounds (status);
CREATE INDEX rounds_opens_at_idx ON rounds (opens_at);
-- the scheduler's hot query: which rounds are due a transition?
CREATE INDEX rounds_due_idx ON rounds (status, seals_at) WHERE status <> 'revealed';

-- ── the state machine, enforced by the database ────────────────────────────
-- §6.1: "the database, not an application timer alone, is authoritative for
-- whether a transition is legal."

CREATE FUNCTION enforce_round_transition() RETURNS trigger AS $$
BEGIN
  IF NEW.status = OLD.status THEN
    RETURN NEW;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM round_transitions
    WHERE from_status = OLD.status AND to_status = NEW.status
  ) THEN
    RAISE EXCEPTION
      'illegal round transition % -> % for round %', OLD.status, NEW.status, OLD.round_id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER rounds_transition_guard
  BEFORE UPDATE OF status ON rounds
  FOR EACH ROW EXECUTE FUNCTION enforce_round_transition();

-- A sealed round's input set is immutable. Reject edits to the fields that
-- define the outcome, no matter which code path attempts them.
CREATE FUNCTION freeze_sealed_round() RETURNS trigger AS $$
BEGIN
  IF OLD.status IN ('sealed', 'resolving', 'revealed')
     AND (NEW.opens_at, NEW.seals_at, NEW.cycle_number, NEW.algorithm_version)
      IS DISTINCT FROM
         (OLD.opens_at, OLD.seals_at, OLD.cycle_number, OLD.algorithm_version)
  THEN
    RAISE EXCEPTION 'round % is sealed; its parameters are immutable', OLD.round_id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER rounds_freeze_guard
  BEFORE UPDATE ON rounds
  FOR EACH ROW EXECUTE FUNCTION freeze_sealed_round();

COMMIT;
