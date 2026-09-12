"""In-memory repositories satisfying the port protocols."""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from domain.lifecycle import RoundStatus, accepts_entries, require_legal
from ports.repositories import (
    CommittedEntry,
    ConcurrentModification,
    Draft,
    RoundNotFound,
    RoundRecord,
)


class RoundClosed(RuntimeError):
    """The round no longer accepts entries — mirrors the database trigger."""


class InMemoryRoundRepository:
    """Satisfies RoundReader and RoundWriter."""

    def __init__(self, now: datetime | None = None) -> None:
        self._rounds: dict[UUID, RoundRecord] = {}
        self._lock = asyncio.Lock()
        self._now = now or datetime.now(UTC)

    async def create(self, record: RoundRecord) -> None:
        async with self._lock:
            if any(r.cycle_number == record.cycle_number for r in self._rounds.values()):
                raise ValueError(f"cycle_number {record.cycle_number} already exists")
            self._rounds[record.round_id] = record

    async def get(self, round_id: UUID) -> RoundRecord:
        try:
            return self._rounds[round_id]
        except KeyError as exc:
            raise RoundNotFound(str(round_id)) from exc

    async def by_cycle(self, cycle_number: int) -> RoundRecord | None:
        return next(
            (r for r in self._rounds.values() if r.cycle_number == cycle_number), None
        )

    async def live(self) -> Sequence[RoundRecord]:
        return sorted(
            (
                r
                for r in self._rounds.values()
                if r.status not in (RoundStatus.REVEALED, RoundStatus.VOIDED)
            ),
            key=lambda r: r.cycle_number,
        )

    async def transition(
        self, round_id: UUID, expected: RoundStatus, to: RoundStatus
    ) -> RoundRecord:
        async with self._lock:
            current = await self.get(round_id)
            if current.status is not expected:
                raise ConcurrentModification(
                    f"round {round_id} is {current.status}, expected {expected}"
                )
            require_legal(current.status, to)
            moved = replace(current, status=to)
            self._rounds[round_id] = moved
            return moved


class InMemoryDraftRepository:
    """Satisfies DraftRepository and DraftScanner."""

    def __init__(self, rounds: InMemoryRoundRepository) -> None:
        self._rounds = rounds
        self._drafts: dict[tuple[UUID, UUID], Draft] = {}
        self._lock = asyncio.Lock()

    async def _require_accepting(self, round_id: UUID) -> None:
        record = await self._rounds.get(round_id)
        if not accepts_entries(record.status):
            raise RoundClosed(f"round {round_id} is {record.status}")

    async def get(self, round_id: UUID, user_id: UUID) -> Draft | None:
        return self._drafts.get((round_id, user_id))

    async def upsert(
        self,
        round_id: UUID,
        user_id: UUID,
        prediction: str | None,
        vote: int | None,
        expected_version: int | None,
    ) -> Draft:
        await self._require_accepting(round_id)
        async with self._lock:
            key = (round_id, user_id)
            existing = self._drafts.get(key)
            if existing is None:
                if expected_version is not None:
                    raise ConcurrentModification(
                        f"no draft to update for user {user_id} in round {round_id}"
                    )
                draft = Draft(round_id, user_id, prediction, vote, 1, datetime.now(UTC))
            else:
                if expected_version is None or expected_version != existing.version:
                    raise ConcurrentModification(
                        f"draft version is {existing.version}, caller had {expected_version}"
                    )
                draft = Draft(
                    round_id, user_id, prediction, vote,
                    existing.version + 1, datetime.now(UTC),
                )
            self._drafts[key] = draft
            return draft

    async def delete(self, round_id: UUID, user_id: UUID) -> None:
        async with self._lock:
            self._drafts.pop((round_id, user_id), None)

    def _complete(self, round_id: UUID) -> list[Draft]:
        # deterministic order: seal-time commit_sequence must be reproducible (F4)
        return sorted(
            (d for (r, _), d in self._drafts.items() if r == round_id and d.is_complete),
            key=lambda d: (d.updated_at, str(d.user_id)),
        )

    async def iter_complete(
        self, round_id: UUID, chunk_size: int
    ) -> AsyncIterator[Sequence[Draft]]:
        rows = self._complete(round_id)
        for i in range(0, len(rows), chunk_size):
            yield rows[i : i + chunk_size]

    async def count_complete(self, round_id: UUID) -> int:
        return len(self._complete(round_id))


class InMemorySubmissionRepository:
    """Satisfies SubmissionReader and SubmissionWriter."""

    def __init__(self, rounds: InMemoryRoundRepository) -> None:
        self._rounds = rounds
        self._by_id: dict[UUID, CommittedEntry] = {}
        self._by_user: dict[tuple[UUID, UUID], UUID] = {}
        self._by_key: dict[tuple[UUID, UUID, str], UUID] = {}
        self._next_seq: dict[UUID, int] = {}
        self._lock = asyncio.Lock()

    async def get_for_user(self, round_id: UUID, user_id: UUID) -> CommittedEntry | None:
        sid = self._by_user.get((round_id, user_id))
        return self._by_id.get(sid) if sid else None

    async def commit_entry(
        self,
        round_id: UUID,
        user_id: UUID,
        prediction: str,
        vote: int,
        mandate_eligible: bool,
        idempotency_key: str | None = None,
    ) -> CommittedEntry:
        record = await self._rounds.get(round_id)
        if not accepts_entries(record.status):
            raise RoundClosed(f"round {round_id} is {record.status}")
        async with self._lock:
            if idempotency_key is not None:
                prior = self._by_key.get((round_id, user_id, idempotency_key))
                if prior is not None:
                    return self._by_id[prior]          # retry returns the same row
            if (round_id, user_id) in self._by_user:
                raise ConcurrentModification(
                    f"user {user_id} already has an entry in round {round_id}"
                )
            seq = self._next_seq.get(round_id, 0) + 1
            self._next_seq[round_id] = seq
            entry = CommittedEntry(
                submission_id=uuid4(),
                round_id=round_id,
                user_id=user_id,
                prediction=prediction,
                vote=vote,
                commit_sequence=seq,
                committed_at=datetime.now(UTC),
                mandate_eligible=mandate_eligible,
            )
            self._by_id[entry.submission_id] = entry
            self._by_user[(round_id, user_id)] = entry.submission_id
            if idempotency_key is not None:
                self._by_key[(round_id, user_id, idempotency_key)] = entry.submission_id
            return entry

    def _round_entries(self, round_id: UUID) -> list[CommittedEntry]:
        return sorted(
            (e for e in self._by_id.values() if e.round_id == round_id),
            key=lambda e: e.commit_sequence,
        )

    async def iter_round(
        self, round_id: UUID, chunk_size: int
    ) -> AsyncIterator[Sequence[CommittedEntry]]:
        rows = self._round_entries(round_id)
        for i in range(0, len(rows), chunk_size):
            yield rows[i : i + chunk_size]

    async def count(self, round_id: UUID) -> int:
        return len(self._round_entries(round_id))
