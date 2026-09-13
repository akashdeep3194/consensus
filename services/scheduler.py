"""The round-lifecycle sweep, and the background loop that runs it on a timer.

Round boundaries are hour-scale (T+23h, T+23.5h, T+24h), not millisecond-scale,
so this deliberately does not reach for a message broker or task queue — the
technique real low-latency schedulers use is a single process that knows the
next deadline and sleeps exactly until then, not a faster poll. That's all
this is: `run_scheduler` computes how long until the soonest boundary any live
round will cross, sleeps for exactly that long, sweeps, and repeats.

`sweep_once` is an ordinary function so POST /api/admin/advance can run the
exact same code path — the endpoint and the background loop are two callers
of one sweep, not two implementations of it.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from domain.lifecycle import RoundStatus
from ports.repositories import RoundRecord
from services.rounds import RoundService
from services.sealing import SealingService

log = logging.getLogger(__name__)

#: Upper bound on how long the loop ever sleeps, even with nothing due — this
#: is what catches a newly-created round, a clock skew, or any missed wake-up,
#: and it's also the fallback interval when no round is live at all.
MAX_SLEEP_SECONDS = 60.0
#: Never spin on a boundary that has technically already arrived.
MIN_SLEEP_SECONDS = 0.5


class SweepTarget(Protocol):
    """The two services a sweep touches. Structural, not api.deps.Container
    itself, so this module never has to import the composition root."""

    rounds: RoundService
    sealing: SealingService


@dataclass(frozen=True, slots=True)
class SweepResult:
    moved: list[tuple[UUID, RoundStatus, RoundStatus]]
    sealed: list[UUID]
    finalized: list[UUID]


async def sweep_once(container: SweepTarget) -> SweepResult:
    """Ensure the current cycle exists, advance anything due, seal anything
    sealing, and finalize (resolve + score) anything sealed.

    Idempotent and safe under concurrent callers: every transition inside is
    compare-and-set (§F5), so the HTTP endpoint and the background loop can
    both call this at the same instant without coordinating.

    `finalize` is attempted for every live round, not only ones this sweep
    just sealed — a round sealed by an earlier sweep that crashed before
    finalizing needs exactly the same retry, and `finalize` itself is a
    no-op (one indexed read) for any round that isn't SEALED/RESOLVING yet.
    """
    moved = await container.rounds.ensure_current()
    sealed: list[UUID] = []
    finalized: list[UUID] = []
    for r in await container.rounds.live():
        if r.status is RoundStatus.SEALING:
            report = await container.sealing.seal(r.round_id)
            sealed.append(report.round_id)
        result = await container.sealing.finalize(r.round_id)
        if result is not None:
            finalized.append(r.round_id)
    return SweepResult(moved=moved, sealed=sealed, finalized=finalized)


def next_boundary(live_rounds: Sequence[RoundRecord], now: datetime) -> datetime | None:
    """The soonest schedule boundary, across every live round, still ahead of `now`.

    Pure and synchronous on purpose: the interesting logic here — "when do we
    next need to wake up" — should be testable with plain RoundRecord/
    RoundSchedule fixtures, with no container, clock injection, or event loop
    required to exercise it.
    """
    def _boundaries(r: RoundRecord):
        s = r.schedule
        return (s.opens_at, s.blackout_at, s.seals_at, s.reveals_at)

    boundaries = (b for r in live_rounds for b in _boundaries(r) if b > now)
    return min(boundaries, default=None)


async def run_scheduler(get_container: Callable[[], SweepTarget]) -> None:
    """Background loop: sleep exactly until the next boundary, sweep, repeat.

    Started as an asyncio task from api.main's lifespan and cancelled on
    shutdown — it runs for the life of the process, not on a fixed interval.
    A failed sweep logs and retries after the safety interval rather than
    taking the loop down; one round's bad data should never silently stop
    every other round from advancing.
    """
    while True:
        try:
            container = get_container()
            now = datetime.now(UTC)
            result = await sweep_once(container)
            nxt = next_boundary(await container.rounds.live(), now)
            sleep_for = (
                MAX_SLEEP_SECONDS
                if nxt is None
                else min(MAX_SLEEP_SECONDS, max(MIN_SLEEP_SECONDS, (nxt - now).total_seconds()))
            )
            log.info(
                "scheduler sweep: moved=%d sealed=%d finalized=%d next_wake_in=%.1fs",
                len(result.moved), len(result.sealed), len(result.finalized), sleep_for,
            )
        except asyncio.CancelledError:
            raise
        except Exception:                        # noqa: BLE001
            log.exception("scheduler sweep failed; retrying after the safety interval")
            sleep_for = MAX_SLEEP_SECONDS
        await asyncio.sleep(sleep_for)
