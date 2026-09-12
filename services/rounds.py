"""Round lifecycle service.

Depends on port Protocols only — it never learns which adapter is installed.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from domain.lifecycle import RoundStatus, next_status
from domain.schedule import DEFAULT_TIMING, RoundTiming, schedule_for
from engine.version import ALGORITHM_VERSION, RULESET_VERSION
from ports.clock import Clock
from ports.repositories import ConcurrentModification, RoundReader, RoundRecord, RoundWriter

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RoundView:
    """What a client is allowed to know about a round right now."""

    round_id: UUID
    cycle_number: int
    status: RoundStatus
    opens_at: datetime
    mandate_deadline: datetime
    blackout_at: datetime
    seals_at: datetime
    reveals_at: datetime
    winning_number: str | None
    commitment_root: str | None
    server_time: datetime

    @classmethod
    def of(cls, r: RoundRecord, now: datetime) -> "RoundView":
        s = r.schedule
        return cls(
            round_id=r.round_id, cycle_number=r.cycle_number, status=r.status,
            opens_at=s.opens_at, mandate_deadline=s.mandate_deadline,
            blackout_at=s.blackout_at, seals_at=s.seals_at, reveals_at=s.reveals_at,
            winning_number=r.winning_number, commitment_root=r.commitment_root,
            server_time=now,
        )


class RoundService:
    def __init__(
        self,
        rounds: RoundReader | RoundWriter,
        clock: Clock,
        anchor: datetime,
        timing: RoundTiming = DEFAULT_TIMING,
    ) -> None:
        self._rounds = rounds
        self._clock = clock
        self._anchor = anchor
        self._timing = timing

    async def ensure_scheduled(self, cycle_number: int) -> RoundRecord:
        """Create a round for `cycle_number` if it does not exist yet."""
        existing = await self._rounds.by_cycle(cycle_number)
        if existing is not None:
            return existing
        record = RoundRecord(
            round_id=uuid4(),
            cycle_number=cycle_number,
            status=RoundStatus.SCHEDULED,
            schedule=schedule_for(cycle_number, self._anchor, self._timing),
            ruleset_version=RULESET_VERSION,
            algorithm_version=ALGORITHM_VERSION,
        )
        await self._rounds.create(record)
        log.info("scheduled round cycle=%s id=%s", cycle_number, record.round_id)
        return record

    async def current(self) -> RoundRecord | None:
        """The round accepting entries right now — the newest that is not sealed."""
        live = await self._rounds.live()
        entering = [r for r in live if r.status in (RoundStatus.OPEN, RoundStatus.BLACKOUT)]
        return max(entering, key=lambda r: r.cycle_number) if entering else None

    async def live(self) -> list[RoundRecord]:
        return list(await self._rounds.live())

    async def advance_due(self) -> list[tuple[UUID, RoundStatus, RoundStatus]]:
        """Move every round whose next phase is due. Idempotent and restartable.

        The schedule says what *should* have happened; the database decides what
        legally can (§6.1). A worker crash mid-sweep is harmless.
        """
        now = self._clock.now()
        moved: list[tuple[UUID, RoundStatus, RoundStatus]] = []
        for record in await self._rounds.live():
            target = record.schedule.status_at(now)
            current = record.status
            # step one phase at a time so no transition is ever skipped
            while current is not target:
                nxt = next_status(current)
                if nxt is None:
                    break
                # don't run ahead of the clock
                if self._phase_rank(nxt) > self._phase_rank(target):
                    break
                try:
                    await self._rounds.transition(record.round_id, current, nxt)
                except ConcurrentModification:
                    break        # another worker got there first; fine
                moved.append((record.round_id, current, nxt))
                current = nxt
        return moved

    @staticmethod
    def _phase_rank(status: RoundStatus) -> int:
        from domain.lifecycle import PROGRESSION

        return PROGRESSION.index(status) if status in PROGRESSION else len(PROGRESSION)
