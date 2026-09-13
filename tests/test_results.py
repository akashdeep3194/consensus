"""services.results — persisting a resolved round's scored outcome.

Regression coverage for the double-counting risk introduced alongside the
auto-resolve fix: SealingService.finalize() (services/sealing.py) is now
called on every scheduler sweep rather than once by a manual admin action, so
a crash-and-retry (or a race between the scheduler and an admin force-seal)
calling record_results twice for the same round must not award anyone points
twice.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from adapters.postgres import PostgresRoundRepository
from domain.lifecycle import RoundStatus
from domain.schedule import schedule_for
from engine import Submission, resolve
from ports.repositories import RoundRecord
from services.results import record_results
from tests.conftest import run

ANCHOR = datetime(2026, 9, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean(pg_pool):
    run(pg_pool.execute(
        "TRUNCATE submissions, round_drafts, round_results, user_seasons, rounds, users CASCADE"
    ))


def _make_round(pool, cycle: int = 1):
    rounds = PostgresRoundRepository(pool)
    rec = RoundRecord(
        round_id=uuid4(),
        cycle_number=cycle,
        status=RoundStatus.REVEALED,
        schedule=schedule_for(cycle, ANCHOR),
        ruleset_version="1.1",
        algorithm_version="1.1.0",
    )
    run(rounds.create(rec))
    return rec.round_id


def _make_user(pool):
    user_id = uuid4()
    run(pool.execute(
        "INSERT INTO users (user_id, external_id, provider) VALUES ($1,$2,'test')",
        user_id, str(user_id),
    ))
    return user_id


def _resolved_result(round_id, user_id):
    submission = Submission(
        round_id=str(round_id),
        submission_id=str(uuid4()),
        user_id=str(user_id),
        prediction=(7, 1, 5),
        vote=7,
        commit_sequence=1,
        mandate_eligible=True,
    )
    return resolve(str(round_id), [submission])


def test_record_results_persists_a_score_and_a_season_row(pg_pool):
    round_id = _make_round(pg_pool)
    user_id = _make_user(pg_pool)
    result = _resolved_result(round_id, user_id)

    run(record_results(pg_pool, round_id, result))

    scored = run(pg_pool.fetchrow(
        "SELECT * FROM round_results WHERE round_id=$1 AND user_id=$2", round_id, user_id
    ))
    assert scored is not None
    season = run(pg_pool.fetchrow("SELECT * FROM user_seasons WHERE user_id=$1", user_id))
    assert season["rounds_played"] == 1
    assert season["total_points"] == scored["points"]


def test_record_results_is_idempotent_and_never_double_counts(pg_pool):
    """The exact risk finalize() introduces: called twice for the same round
    (a retried sweep, or a race with a manual admin seal) must not award
    points twice, and must not inflate rounds_played."""
    round_id = _make_round(pg_pool)
    user_id = _make_user(pg_pool)
    result = _resolved_result(round_id, user_id)

    run(record_results(pg_pool, round_id, result))
    run(record_results(pg_pool, round_id, result))   # a second, redundant call

    season = run(pg_pool.fetchrow("SELECT * FROM user_seasons WHERE user_id=$1", user_id))
    assert season["rounds_played"] == 1, "a repeat call must not double-count the season"
