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


@dataclass(frozen=True, slots=True)
class RoundPage:
    """One page of round history, plus the cursor for the next one."""

    rounds: list[RoundRecord]
    next_before_cycle: int | None


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

    async def ensure_current(self) -> list[tuple[UUID, RoundStatus, RoundStatus]]:
        """Make sure the cycle for right now exists, and advance anything due.

        The one entry point for "bring the round state up to date," called by
        both the request path (api.main, on nearly every route) and the
        background scheduler (services.scheduler) — whichever gets here first
        for a given moment does the same work, and every transition
        underneath is compare-and-set, so calling this from both at once is
        harmless (§F5).
        """
        now = self._clock.now()
        elapsed = now - self._anchor
        cycle = max(0, int(elapsed // self._timing.cadence))
        for c in {max(0, cycle - 1), cycle}:
            await self.ensure_scheduled(c)
        moved = await self.advance_due()
        await self.ensure_open_round()
        return moved

    async def current(self) -> RoundRecord | None:
        """The round accepting entries right now — the newest that is not sealed."""
        live = await self._rounds.live()
        entering = [r for r in live if r.status in (RoundStatus.OPEN, RoundStatus.BLACKOUT)]
        return max(entering, key=lambda r: r.cycle_number) if entering else None

    async def live(self) -> list[RoundRecord]:
        return list(await self._rounds.live())

    async def ensure_open_round(self) -> RoundRecord | None:
        """Guarantee some round is OPEN or BLACKOUT, minting the next cycle
        if nothing is. Returns the round it opened, or None when something
        was already live (the normal case: two rounds are live at once by
        design — domain.schedule's daily overlap — so this is usually a
        no-op).

        The self-healing half of ensure_current: a stale anchor, a voided
        round with nothing behind it, or any other gap that leaves nothing
        live is closed here rather than requiring an operator to notice and
        force a round open by hand. Deliberately anchor-independent — it
        picks highest_cycle()+1, not anything derived from (now - anchor),
        since anchor-derived arithmetic is exactly what got this wrong in
        the first place (services/anchor.py).

        Safe under concurrent callers: losing the create() race (unique
        cycle_number) or the transition() race (compare-and-set) both mean
        another caller already achieved the one thing this exists to
        guarantee, so both are caught rather than raised.
        """
        live = await self._rounds.live()
        if any(r.status in (RoundStatus.OPEN, RoundStatus.BLACKOUT) for r in live):
            return None

        highest = await self._rounds.highest_cycle()
        try:
            record = await self.ensure_scheduled(highest + 1)
        except ValueError:
            record = await self._rounds.by_cycle(highest + 1)
            if record is None:
                raise

        if record.status is RoundStatus.SCHEDULED:
            try:
                record = await self._rounds.transition(
                    record.round_id, RoundStatus.SCHEDULED, RoundStatus.OPEN
                )
            except ConcurrentModification:
                record = await self._rounds.get(record.round_id)
        return record

    async def history(
        self, before_cycle: int | None = None, limit: int = 20
    ) -> RoundPage:
        """One page of past results, newest first.

        Fetches one extra row beyond `limit` purely to know whether another
        page exists — `next_before_cycle` is only ever non-None when a
        further page is actually there, so a caller can never show a "load
        more" control that leads to nothing.
        """
        fetched = await self._rounds.history(before_cycle, limit + 1)
        has_more = len(fetched) > limit
        rounds = list(fetched[:limit])
        next_cursor = rounds[-1].cycle_number if has_more else None
        return RoundPage(rounds=rounds, next_before_cycle=next_cursor)

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
                if current in (RoundStatus.SEALING, RoundStatus.SEALED):
                    # SEALING -> SEALED (drafts materialised, commitment root
                    # set) and SEALED -> RESOLVING (winning number persisted)
                    # each do real work that only SealingService.seal()/
                    # .finalize() may perform — never a bare status flip, no
                    # matter how large the gap since the last sweep. Parking
                    # here is always safe: sweep_once calls seal()/finalize()
                    # on every live round, every sweep, regardless of what
                    # advance_due did this time.
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
