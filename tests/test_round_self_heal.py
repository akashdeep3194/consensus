"""RoundService.ensure_open_round / ensure_current's self-healing.

Regression coverage for the production incident: nothing in the passive path
used to ever open a fresh round when none was live — only the manual admin
force-seal endpoint could. A stale anchor (services/anchor.py fixes that
separately), a voided round with nothing behind it, or any other gap left
the game stalled until an operator noticed. ensure_current must now recover
on its own, and the cycle number it picks must come from the table itself
(highest_cycle), never from (now - anchor) — anchor-derived arithmetic is
exactly what caused the incident in the first place.
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


def _service(round_repo=None, clock=None):
    return RoundService(
        round_repo or InMemoryRoundRepository(), clock or FixedClock(ANCHOR),
        ANCHOR, DEFAULT_TIMING,
    )


def _round(round_repo, cycle, status=RoundStatus.OPEN, winning_number=None):
    rec = RoundRecord(
        round_id=uuid4(), cycle_number=cycle, status=status,
        schedule=schedule_for(cycle, ANCHOR), ruleset_version="1.1",
        algorithm_version="1.1.0",
    )
    run(round_repo.create(rec))
    if winning_number is not None:
        run(round_repo.record_resolution(rec.round_id, winning_number))
    return rec


def test_ensure_open_round_is_a_noop_when_something_is_live():
    round_repo = InMemoryRoundRepository()
    _round(round_repo, cycle=0, status=RoundStatus.OPEN)
    service = _service(round_repo)

    assert run(service.ensure_open_round()) is None
    assert run(round_repo.highest_cycle()) == 0, "must not mint a round nobody asked for"


def test_ensure_open_round_opens_the_next_cycle_when_nothing_is_live():
    round_repo = InMemoryRoundRepository()
    _round(round_repo, cycle=3, status=RoundStatus.REVEALED, winning_number="123")
    service = _service(round_repo)

    opened = run(service.ensure_open_round())

    assert opened is not None
    assert opened.cycle_number == 4
    assert opened.status is RoundStatus.OPEN


def test_ensure_open_round_is_anchor_independent():
    """The actual bug: a stale anchor makes (now - anchor) meaningless. The
    next cycle must come from the table's own highest cycle number, not from
    anchor arithmetic that would compute something wildly different here."""
    round_repo = InMemoryRoundRepository()
    _round(round_repo, cycle=100, status=RoundStatus.REVEALED, winning_number="123")
    # "now" sits right at the anchor, so (now - anchor)/cadence == 0 — anchor
    # arithmetic alone would suggest cycle 0, not 101.
    service = _service(round_repo, clock=FixedClock(ANCHOR))

    opened = run(service.ensure_open_round())

    assert opened.cycle_number == 101


def test_ensure_open_round_is_idempotent():
    """A second call, once the first has already opened something, must be
    a no-op — not a second attempt to mint the same cycle number again."""
    round_repo = InMemoryRoundRepository()
    _round(round_repo, cycle=0, status=RoundStatus.REVEALED, winning_number="123")
    service = _service(round_repo)

    first = run(service.ensure_open_round())
    second = run(service.ensure_open_round())

    assert first is not None
    assert second is None
    assert run(round_repo.highest_cycle()) == 1, "must not mint a second round"


def test_ensure_current_self_heals_after_everything_is_voided():
    round_repo = InMemoryRoundRepository()
    rec = _round(round_repo, cycle=0, status=RoundStatus.OPEN)
    run(round_repo.transition(rec.round_id, RoundStatus.OPEN, RoundStatus.VOIDED))
    service = _service(round_repo)

    assert run(service.current()) is None, "the stuck precondition"

    run(service.ensure_current())

    healed = run(service.current())
    assert healed is not None
    assert healed.cycle_number == 1
