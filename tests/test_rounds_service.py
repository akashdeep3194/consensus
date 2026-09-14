"""RoundService.history — the pagination composed on top of the port method.

The port's own history() is exercised for correctness (ordering, filtering,
cursor semantics) in tests/test_port_conformance.py; what's specific to the
service layer is the "peek one extra row" trick that decides next_before_cycle,
so that's what these tests cover.
"""

from datetime import UTC, datetime
from uuid import uuid4

from adapters.memory import InMemoryRoundRepository
from domain.lifecycle import RoundStatus
from domain.schedule import DEFAULT_TIMING, schedule_for
from ports.clock import FixedClock
from ports.repositories import RoundRecord
from services.rounds import RoundService
from tests.conftest import run

ANCHOR = datetime(2026, 9, 12, tzinfo=UTC)


def _service_with_revealed_rounds(n: int) -> RoundService:
    round_repo = InMemoryRoundRepository()
    service = RoundService(round_repo, FixedClock(ANCHOR), ANCHOR, DEFAULT_TIMING)
    for cycle in range(n):
        rec = RoundRecord(
            round_id=uuid4(), cycle_number=cycle, status=RoundStatus.REVEALED,
            schedule=schedule_for(cycle, ANCHOR),
            ruleset_version="1.1", algorithm_version="1.1.0",
        )
        run(round_repo.create(rec))
        run(round_repo.record_resolution(rec.round_id, "123"))
        # history()'s "at least one vote" filter needs one on record — this
        # suite is about the pagination built on top, not that filter itself
        # (tests/test_port_conformance.py owns that), so every round here
        # gets one unconditionally.
        round_repo.record_vote(rec.round_id)
    return service


def test_next_before_cycle_is_none_when_everything_fits_on_one_page():
    service = _service_with_revealed_rounds(3)
    page = run(service.history(limit=10))
    assert len(page.rounds) == 3
    assert page.next_before_cycle is None


def test_next_before_cycle_points_at_a_real_further_page():
    service = _service_with_revealed_rounds(5)
    first = run(service.history(limit=2))
    assert [r.cycle_number for r in first.rounds] == [4, 3]
    assert first.next_before_cycle == 3

    second = run(service.history(before_cycle=first.next_before_cycle, limit=2))
    assert [r.cycle_number for r in second.rounds] == [2, 1]
    assert second.next_before_cycle == 1

    last = run(service.history(before_cycle=second.next_before_cycle, limit=2))
    assert [r.cycle_number for r in last.rounds] == [0]
    assert last.next_before_cycle is None, "nothing left — must never invite another page"
