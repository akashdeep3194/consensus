"""Repository contracts.

Split by role rather than by table: a reader cannot write. Each Protocol is
small enough to implement fully, which is what keeps substitutes honest.

`Draft` and `RoundRecord` are plain data carried across the boundary, so the
core never handles driver-specific row objects.
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from domain.lifecycle import RoundStatus
from domain.schedule import RoundSchedule


class ConcurrentModification(RuntimeError):
    """Optimistic-concurrency conflict: the row moved under us (§5.2)."""


class RoundNotFound(LookupError):
    pass


class RoundClosed(RuntimeError):
    """The round no longer accepts entries (§6.2).

    Part of the contract, not an adapter detail: every adapter must raise this
    same type, so callers never branch on which implementation is installed.
    """


@dataclass(frozen=True, slots=True)
class RoundRecord:
    round_id: UUID
    cycle_number: int
    status: RoundStatus
    schedule: RoundSchedule
    ruleset_version: str
    algorithm_version: str
    commitment_root: str | None = None
    winning_number: str | None = None


@dataclass(frozen=True, slots=True)
class Draft:
    round_id: UUID
    user_id: UUID
    prediction: str | None
    vote: int | None
    version: int
    updated_at: datetime

    @property
    def is_complete(self) -> bool:
        """Mirrors the generated column of the same name (F6)."""
        return self.prediction is not None and self.vote is not None


@dataclass(frozen=True, slots=True)
class CommittedEntry:
    submission_id: UUID
    round_id: UUID
    user_id: UUID
    prediction: str
    vote: int
    commit_sequence: int
    committed_at: datetime
    mandate_eligible: bool
    voided_at: datetime | None = None


# ── rounds ─────────────────────────────────────────────────────────────────


@runtime_checkable
class RoundReader(Protocol):
    async def get(self, round_id: UUID) -> RoundRecord: ...
    async def by_cycle(self, cycle_number: int) -> RoundRecord | None: ...
    async def live(self) -> Sequence[RoundRecord]:
        """Rounds that have opened but not yet revealed. Usually two (Q3)."""
        ...

    async def history(
        self, before_cycle: int | None, limit: int
    ) -> Sequence[RoundRecord]:
        """REVEALED rounds with a persisted result, newest first, at most `limit`.

        `before_cycle` (exclusive) is the keyset-pagination cursor — omit it
        for the first page. A round that reached REVEALED without ever being
        resolved has no result to show and is excluded, the same treatment
        VOIDED already gets. So is a round nobody voted in at all: with every
        digit's count at zero, engine.rank.winning_number's tie-break still
        returns a number (0, 1, 2) — a real value, but not a real result — so
        a round needs at least one committed vote to qualify.
        """
        ...

    async def highest_cycle(self) -> int:
        """Greatest cycle_number in the table, -1 if it is empty.

        Anchor-independent by design — the reliable way to pick "the next
        cycle to open" when self-healing (services.rounds.RoundService.
        ensure_open_round), since anchor-derived arithmetic is exactly what a
        stale anchor got wrong (services/anchor.py).
        """
        ...


@runtime_checkable
class RoundWriter(Protocol):
    async def create(self, record: RoundRecord) -> None: ...
    async def transition(
        self, round_id: UUID, expected: RoundStatus, to: RoundStatus
    ) -> RoundRecord:
        """Atomically move a round, failing if it is no longer at `expected`.

        Compare-and-set rather than read-then-write: the check and the change
        must be one operation or two workers can both believe they won.
        """
        ...

    async def seal_with_root(self, round_id: UUID, commitment_root: str) -> RoundRecord:
        """SEALING -> SEALED, recording the commitment in the same operation.

        One step, not two. The root only becomes valid at the instant the input
        set is final, and a round must never exist in a sealed state without the
        commitment that covers it — a crash between two statements would leave
        exactly that hole.
        """
        ...

    async def record_resolution(self, round_id: UUID, winning_number: str) -> None: ...


# ── drafts ─────────────────────────────────────────────────────────────────


@runtime_checkable
class DraftRepository(Protocol):
    async def get(self, round_id: UUID, user_id: UUID) -> Draft | None: ...
    async def upsert(
        self,
        round_id: UUID,
        user_id: UUID,
        prediction: str | None,
        vote: int | None,
        expected_version: int | None,
    ) -> Draft:
        """Create or update a draft under optimistic concurrency.

        `expected_version=None` creates. A mismatch raises
        ConcurrentModification so two tabs cannot silently overwrite (§6.2).
        """
        ...

    async def delete(self, round_id: UUID, user_id: UUID) -> None: ...


@runtime_checkable
class DraftScanner(Protocol):
    """Bulk read over every complete draft in a round.

    Two callers, one contract: the sealing worker's materialisation, and the
    live standings endpoint (there is no manual lock-in, so during OPEN a
    draft *is* the only record of a cast vote — see EntryService.metrics_for).
    """

    async def iter_complete(
        self, round_id: UUID, chunk_size: int
    ) -> AsyncIterator[Sequence[Draft]]:
        """Complete drafts in a deterministic order, in chunks (F5)."""
        ...

    async def count_complete(self, round_id: UUID) -> int: ...


@runtime_checkable
class DraftStore(DraftRepository, DraftScanner, Protocol):
    """Everything a draft-facing caller needs: edit one, and bulk-scan many.

    Named separately from its two parents because EntryService is the one
    caller that genuinely needs both halves at once (ordinary draft edits,
    plus the live-standings scan) — an adapter satisfies this the same way it
    always has, by implementing every method on one class.
    """


# ── submissions ────────────────────────────────────────────────────────────


@runtime_checkable
class SubmissionReader(Protocol):
    async def get_for_user(self, round_id: UUID, user_id: UUID) -> CommittedEntry | None: ...
    async def iter_round(
        self, round_id: UUID, chunk_size: int
    ) -> AsyncIterator[Sequence[CommittedEntry]]:
        """The round's entries in commit_sequence order — the resolver's input."""
        ...

    async def count(self, round_id: UUID) -> int: ...


@runtime_checkable
class SubmissionWriter(Protocol):
    async def commit_entry(
        self,
        round_id: UUID,
        user_id: UUID,
        prediction: str,
        vote: int,
        mandate_eligible: bool,
        idempotency_key: str | None,
    ) -> CommittedEntry:
        """Commit one entry. Idempotent: retrying a key returns the existing row."""
        ...
