"""services.scheduler — the sweep and the background loop's timing logic.

next_boundary is what makes this event-driven rather than polling: these
tests are what prove it actually wakes up at the right instant instead of on
some fixed interval.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.lifecycle import RoundStatus
from domain.schedule import schedule_for
from ports.repositories import RoundRecord
from services.scheduler import MAX_SLEEP_SECONDS, next_boundary

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
