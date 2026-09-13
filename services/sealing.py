"""Sealing and resolution.

F5: atomicity and restartability are reconciled by making the **status
transition** the atomic moment, not the data movement.

    OPEN/BLACKOUT -> SEALING   one small transaction; establishes the cutoff
    ... chunked, idempotent materialisation of every complete draft ...
    reconcile counts
    SEALING -> SEALED          only once materialisation is verified complete

A crash at any point is safe: the cutoff already happened, and every chunk is
idempotent, so a restart resumes rather than duplicating.

There is no manual lock-in (§6): a draft is freely editable for as long as the
round accepts entries, and materialisation here is the one and only place a
draft becomes a committed entry — applied uniformly to whatever every player's
draft holds at that instant.
"""

import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from domain.lifecycle import RoundStatus, next_status
from engine import Submission, resolve
from engine.resolve import RoundResult
from ports.clock import Clock
from ports.repositories import ConcurrentModification

log = logging.getLogger(__name__)

CHUNK = 1000

RecordResults = Callable[[UUID, RoundResult], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class SealReport:
    round_id: UUID
    drafts_committed: int
    total_submissions: int
    commitment_root: str


class SealingService:
    def __init__(
        self, rounds, drafts, submissions, clock: Clock,
        record_results: RecordResults | None = None,
    ) -> None:
        self._rounds = rounds
        self._drafts = drafts
        self._submissions = submissions
        self._clock = clock
        # Optional: persisting round_results/user_seasons is a reporting
        # concern, not core game state, so it's injected rather than a hard
        # port dependency — finalize() works (minus that rollup) even when
        # this is left unset, which is all the conformance/unit tests need.
        self._record_results = record_results

    async def seal(self, round_id: UUID) -> SealReport:
        """Seal a round. Safe to call repeatedly and safe to resume after a crash."""
        record = await self._rounds.get(round_id)

        if record.status in (RoundStatus.OPEN, RoundStatus.BLACKOUT):
            # Walk the progression one legal step at a time. A round may never
            # skip blackout — that phase is a rule, not a formality — so sealing
            # from OPEN passes through it rather than jumping.
            record = await self._advance_to(record, RoundStatus.SEALING)

        if record.status is RoundStatus.SEALING:
            committed = await self._materialise(round_id, record)
        else:
            committed = 0

        total = await self._submissions.count(round_id)
        result = await self.resolve_round(round_id, persist=False)

        if record.status is RoundStatus.SEALING:
            # one operation: the round becomes sealed and gains its commitment
            # together, so it can never be sealed without one
            await self._rounds.seal_with_root(round_id, result.commitment_root)

        log.info(
            "sealed round=%s auto_committed=%s total=%s root=%s",
            round_id, committed, total, result.commitment_root[:16],
        )
        return SealReport(round_id, committed, total, result.commitment_root)

    async def finalize(self, round_id: UUID) -> RoundResult | None:
        """Resolve, persist the winning number, and walk a sealed round the
        rest of the way to REVEALED — the steps `seal()` deliberately stops
        short of (§F5: sealing and resolution are separate concerns).

        This is the missing half of the automatic pipeline: previously only
        the admin force-seal endpoint ever called `resolve_round(persist=True)`
        or recorded results, so a round left to the scheduler alone would
        reach REVEALED with no winning number and no scored entries. This
        closes that gap — `sweep_once` (services.scheduler) now calls this
        for every live round every sweep, unconditionally.

        Idempotent: a round not yet SEALED, or already REVEALED, is a no-op
        (returns None). Safe under light concurrency: losing the final
        transition to a caller who got there first (e.g. an admin force-seal
        racing the passive scheduler) is treated the same way
        RoundService.advance_due() already treats it — fine, not an error.
        """
        record = await self._rounds.get(round_id)
        if record.status not in (RoundStatus.SEALED, RoundStatus.RESOLVING):
            return None
        # resolve_round(persist=True) writes the winning number and, if the
        # round was still SEALED, advances it to RESOLVING itself — re-fetch
        # rather than assume, so the transition below acts on the true status.
        result = await self.resolve_round(round_id, persist=True)
        record = await self._rounds.get(round_id)
        if record.status is RoundStatus.RESOLVING:
            with contextlib.suppress(ConcurrentModification):
                await self._rounds.transition(
                    round_id, RoundStatus.RESOLVING, RoundStatus.REVEALED
                )
        if self._record_results is not None:
            await self._record_results(round_id, result)
        return result

    async def _advance_to(self, record, target: RoundStatus):
        """Step a round forward to `target`, honouring every intermediate phase."""
        while record.status is not target:
            nxt = next_status(record.status)
            if nxt is None:
                raise RuntimeError(f"cannot reach {target} from {record.status}")
            record = await self._rounds.transition(record.round_id, record.status, nxt)
        return record

    async def _materialise(self, round_id: UUID, record) -> int:
        """Commit every complete remaining draft, in chunks. This is the only
        way a draft ever becomes an entry (§6): there is no manual lock-in, so
        every player crosses DRAFT -> COMMITTED at the same instant, right here.

        Drafts are scanned in the canonical (updated_at, user_id) order so the
        commit_sequence values an auditor derives match ours (F4).
        """
        committed = 0
        async for chunk in self._drafts.iter_complete(round_id, CHUNK):
            for draft in chunk:
                try:
                    await self._submissions.commit_entry(
                        round_id,
                        draft.user_id,
                        draft.prediction,
                        draft.vote,
                        # Ruleset §3.2: Board B counts only entries whose slate
                        # was already settled before T+12h. With no manual
                        # lock-in, "settled" means "not edited since" — the
                        # draft's own last-write timestamp, not the moment it
                        # happens to be swept up here.
                        mandate_eligible=record.schedule.mandate_eligible(draft.updated_at),
                        idempotency_key=f"seal:{round_id}:{draft.user_id}",
                    )
                    committed += 1
                except Exception:                    # noqa: BLE001
                    log.exception("failed to auto-commit draft user=%s", draft.user_id)
                    raise
                await self._drafts.delete(round_id, draft.user_id)
        return committed

    async def resolve_round(self, round_id: UUID, persist: bool = True) -> RoundResult:
        """Run the deterministic resolver over the committed set."""
        entries: list[Submission] = []
        async for chunk in self._submissions.iter_round(round_id, CHUNK):
            for e in chunk:
                if e.voided_at is not None:
                    continue                         # voided entries leave the input set
                entries.append(
                    Submission(
                        round_id=str(round_id),
                        submission_id=str(e.submission_id),
                        user_id=str(e.user_id),
                        prediction=tuple(int(c) for c in e.prediction),
                        vote=e.vote,
                        commit_sequence=e.commit_sequence,
                        mandate_eligible=e.mandate_eligible,
                    )
                )
        result = resolve(str(round_id), entries)

        if persist:
            record = await self._rounds.get(round_id)
            if record.status is RoundStatus.SEALED:
                await self._rounds.transition(
                    round_id, RoundStatus.SEALED, RoundStatus.RESOLVING
                )
            await self._rounds.record_resolution(
                round_id, "".join(str(d) for d in result.winning_number)
            )
        return result
