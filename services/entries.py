"""Draft editing and lock-in.

The transactional heart of the game (§5). Everything here goes through ports,
so the same service runs against Postgres in production and in-memory in tests.
"""

import logging
from dataclasses import dataclass
from uuid import UUID

from domain.lifecycle import RoundStatus, accepts_entries
from engine import InvalidPrediction, validate_prediction, validate_vote
from ports.clock import Clock
from ports.repositories import (
    CommittedEntry,
    Draft,
    DraftRepository,
    RoundClosed,
    RoundReader,
    SubmissionReader,
    SubmissionWriter,
)

log = logging.getLogger(__name__)


class AlreadyCommitted(RuntimeError):
    """The player has locked in; a committed entry can never be edited (§1.3)."""


class IncompleteEntry(ValueError):
    """Lock-in needs both a prediction and a vote."""


def parse_slate(text: str) -> tuple[int, int, int]:
    """'527' -> (5,2,7), rejecting anything that is not three distinct digits."""
    if not isinstance(text, str) or len(text) != 3 or not text.isdigit():
        raise InvalidPrediction(f"prediction must be three digits, got {text!r}")
    return validate_prediction(tuple(int(c) for c in text))


@dataclass(frozen=True, slots=True)
class EntryState:
    """A player's position in a round: at most one draft or one committed entry."""

    draft: Draft | None
    committed: CommittedEntry | None

    @property
    def is_locked(self) -> bool:
        return self.committed is not None


class EntryService:
    def __init__(
        self,
        rounds: RoundReader,
        drafts: DraftRepository,
        submissions: SubmissionReader | SubmissionWriter,
        clock: Clock,
    ) -> None:
        self._rounds = rounds
        self._drafts = drafts
        self._submissions = submissions
        self._clock = clock

    async def state(self, round_id: UUID, user_id: UUID) -> EntryState:
        committed = await self._submissions.get_for_user(round_id, user_id)
        if committed is not None:
            return EntryState(draft=None, committed=committed)
        return EntryState(draft=await self._drafts.get(round_id, user_id), committed=None)

    async def save_draft(
        self,
        round_id: UUID,
        user_id: UUID,
        prediction: str | None,
        vote: int | None,
        expected_version: int | None,
    ) -> Draft:
        """Durably save a draft. Returns only after PostgreSQL has committed (§4.2)."""
        record = await self._rounds.get(round_id)
        if not accepts_entries(record.status):
            raise RoundClosed(f"round is {record.status}")
        if (await self._submissions.get_for_user(round_id, user_id)) is not None:
            raise AlreadyCommitted("entry is locked in and cannot be edited")

        if prediction is not None:
            parse_slate(prediction)                    # validate before persisting
        if vote is not None:
            validate_vote(vote)
        return await self._drafts.upsert(
            round_id, user_id, prediction, vote, expected_version
        )

    async def lock_in(
        self,
        round_id: UUID,
        user_id: UUID,
        idempotency_key: str | None = None,
    ) -> CommittedEntry:
        """Commit the player's draft. DRAFT -> COMMITTED, irreversible (§5.1)."""
        record = await self._rounds.get(round_id)
        if not accepts_entries(record.status):
            raise RoundClosed(f"round is {record.status}")

        existing = await self._submissions.get_for_user(round_id, user_id)
        if existing is not None:
            return existing                            # idempotent by nature

        draft = await self._drafts.get(round_id, user_id)
        if draft is None or not draft.is_complete:
            raise IncompleteEntry("a prediction and a vote are both required")

        parse_slate(draft.prediction)
        validate_vote(draft.vote)

        eligible = record.schedule.mandate_eligible(self._clock.now())
        entry = await self._submissions.commit_entry(
            round_id, user_id, draft.prediction, draft.vote, eligible, idempotency_key
        )
        await self._drafts.delete(round_id, user_id)
        log.info(
            "locked in round=%s user=%s seq=%s mandate=%s",
            round_id, user_id, entry.commit_sequence, eligible,
        )
        return entry

    async def metrics_for(self, round_id: UUID) -> dict | None:
        """Live vote standings — the coordination signal (ruleset §5).

        Returns None during blackout and after: the dark hour serves nothing
        rather than serving something subtly different (F8).
        """
        record = await self._rounds.get(round_id)
        if record.status is not RoundStatus.OPEN:
            return None
        counts = [0] * 10
        total = 0
        async for chunk in self._submissions.iter_round(round_id, 1000):
            for e in chunk:
                if e.voided_at is None:
                    counts[e.vote] += 1
                    total += 1
        return {"counts": counts, "total": total}
