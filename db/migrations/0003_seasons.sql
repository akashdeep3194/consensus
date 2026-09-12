-- ═══════════════════════════════════════════════════════════════════════════
-- Season scoring: what a win is worth (Q8).
-- Points and streaks, deliberately not money — no payments, no custody, no
-- regulatory surface. Derived from results, so it can always be recomputed.
-- ═══════════════════════════════════════════════════════════════════════════

BEGIN;

CREATE TABLE round_results (
  round_id       uuid NOT NULL REFERENCES rounds ON DELETE CASCADE,
  user_id        uuid NOT NULL REFERENCES users  ON DELETE CASCADE,
  tier           text NOT NULL,
  points         integer NOT NULL,
  streak_after   integer NOT NULL,
  mandate_score  bigint NOT NULL,
  mandate_rank   integer,
  recorded_at    timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (round_id, user_id),
  CONSTRAINT points_non_negative CHECK (points >= 0),
  CONSTRAINT streak_non_negative CHECK (streak_after >= 0)
);

CREATE INDEX round_results_user_idx ON round_results (user_id, recorded_at DESC);
CREATE INDEX round_results_board_idx ON round_results (round_id, mandate_rank)
  WHERE mandate_rank IS NOT NULL;

-- Running totals. A cache of round_results, rebuildable at any time.
CREATE TABLE user_seasons (
  user_id       uuid PRIMARY KEY REFERENCES users ON DELETE CASCADE,
  total_points  bigint NOT NULL DEFAULT 0,
  streak        integer NOT NULL DEFAULT 0,
  best_streak   integer NOT NULL DEFAULT 0,
  trifectas     integer NOT NULL DEFAULT 0,
  boxed         integer NOT NULL DEFAULT 0,
  rounds_played integer NOT NULL DEFAULT 0,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT totals_non_negative CHECK (
    total_points >= 0 AND streak >= 0 AND best_streak >= streak
  )
);

CREATE INDEX user_seasons_leaderboard_idx ON user_seasons (total_points DESC);

COMMIT;
