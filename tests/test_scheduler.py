"""services.scheduler — the sweep and the background loop's timing logic.

next_boundary is what makes this event-driven rather than polling: these
tests are what prove it actually wakes up at the right instant instead of on
some fixed interval.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from adapters.memory import (
    InMemoryDraftRepository,
    InMemoryRoundRepository,
    InMemorySubmissionRepository,
)
from domain.lifecycle import RoundStatus
from domain.schedule import DEFAULT_TIMING, schedule_for
from ports.clock import FixedClock
from ports.repositories import RoundRecord
from services.rounds import RoundService
from services.scheduler import MAX_SLEEP_SECONDS, next_boundary, sweep_once
from services.sealing import SealingService
from tests.conftest import run

ANCHOR = datetime(2026, 9, 12, tzinfo=UTC)


def make_round(cycle: int, status: RoundStatus = RoundStatus.OPEN) -> RoundRecord:
    return RoundRecord(
        round_id=uuid4(),
        cycle_number=cycle,
        status=status,
        schedule=schedule_for(cycle, ANCHOR),
        ruleset_version="1.1",
        algorithm_version="1.1.0",
    )


def test_next_boundary_is_the_soonest_one_still_ahead():
    r = make_round(0)
    now = ANCHOR + timedelta(hours=1)
    assert next_boundary([r], now) == r.schedule.blackout_at


def test_next_boundary_skips_boundaries_already_passed():
    r = make_round(0)
    now = r.schedule.blackout_at + timedelta(minutes=1)
    assert next_boundary([r], now) == r.schedule.seals_at


def test_next_boundary_across_multiple_live_rounds():
    """The daily overlap (§Q3-adjacent): two rounds live at once, the nearer
    round's boundary wins even though it opened later."""
    older, newer = make_round(0), make_round(1)
    now = newer.schedule.opens_at   # the handoff instant — see test_schedule.py
    assert next_boundary([older, newer], now) == newer.schedule.blackout_at


def test_next_boundary_is_none_with_nothing_live():
    assert next_boundary([], ANCHOR) is None


def test_next_boundary_is_none_once_every_boundary_has_passed():
    r = make_round(0)
    assert next_boundary([r], r.schedule.reveals_at) is None


def test_max_sleep_is_a_real_upper_bound_not_a_typo():
    """A sanity check on the constant itself: this is what the loop falls
    back to with nothing live, so it must be short enough to notice a
    newly-created round promptly, not just a large placeholder number."""
    assert 0 < MAX_SLEEP_SECONDS <= 300


# ── sweep_once: sealing must not be the end of the line ─────────────────
#
# Regression coverage for a real gap: only the admin force-seal endpoint used
# to ever resolve a round (persist a winning number), record results, or walk
# it from RESOLVING to REVEALED. A round left to the scheduler alone reached
# REVEALED with none of that ever having happened. sweep_once must now finish
# the job by itself — these tests build the sweep's two dependencies directly
# against the in-memory adapters, so they exercise real service objects
# without needing a database or real elapsed wall-clock time (finalize()
# itself is never gated on the clock, only on a round's current status).


@dataclass
class _Container:
    """The two attributes services.scheduler.SweepTarget requires."""

    rounds: RoundService
    sealing: SealingService


def _sweepable_round():
    """One OPEN round with a single complete draft, ready to be sealed."""
    round_repo = InMemoryRoundRepository()
    draft_repo = InMemoryDraftRepository(round_repo)
    sub_repo = InMemorySubmissionRepository(round_repo)
    clock = FixedClock(ANCHOR)

    rounds = RoundService(round_repo, clock, ANCHOR, DEFAULT_TIMING)
    sealing = SealingService(round_repo, draft_repo, sub_repo, clock)

    record = run(rounds.ensure_scheduled(0))
    run(round_repo.transition(record.round_id, RoundStatus.SCHEDULED, RoundStatus.OPEN))
    run(draft_repo.upsert(record.round_id, uuid4(), "715", 7, None))

    return record.round_id, _Container(rounds=rounds, sealing=sealing), round_repo


def test_sweep_once_resolves_and_reveals_a_sealed_round_on_its_own():
    """The actual bug: sealing alone must not be where a round stalls."""
    round_id, container, round_repo = _sweepable_round()
    run(container.sealing.seal(round_id))  # -> SEALED, same as force_seal used to require next

    result = run(sweep_once(container))

    assert round_id in result.finalized
    record = run(round_repo.get(round_id))
    assert record.status is RoundStatus.REVEALED
    assert record.winning_number is not None and len(record.winning_number) == 3


def test_sweep_once_finalize_is_idempotent_once_revealed():
    round_id, container, _ = _sweepable_round()
    run(container.sealing.seal(round_id))
    run(sweep_once(container))                 # first sweep finalizes it

    second = run(sweep_once(container))         # nothing left to do

    assert second.finalized == []
