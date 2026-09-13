"""Draft editing and live standings.

The transactional heart of the game (§5). Everything here goes through ports,
so the same service runs against Postgres in production and in-memory in tests.

There is no user-initiated lock-in. A draft is freely editable for as long as
the round accepts entries — right up to the same instant for everyone — and
crosses over to a committed entry only once, automatically, when the round
seals (services.sealing.SealingService._materialise). Nothing here can commit
one on demand.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from domain.lifecycle import RoundStatus, accepts_entries
from engine import InvalidPrediction, validate_prediction, validate_vote
from ports.clock import Clock
from ports.repositories import (
    CommittedEntry,
    Draft,
    DraftStore,
    RoundClosed,
    RoundReader,
    SubmissionReader,
)

log = logging.getLogger(__name__)

#: How long a standings snapshot is served before the next poll recomputes it.
#: A deliberate coarsening (ruleset §5 wants a coordination signal, not a
#: per-request aggregate): without it, every connected player's ~4s poll
#: re-scanned every complete draft in the round from scratch — O(players)
#: work done O(players) times per window, the one thing that would not have
#: survived real concurrent load.
STANDINGS_REFRESH_SECONDS = 300


class AlreadyCommitted(RuntimeError):
    """The round already committed this entry; it can never be edited (§1.3).

    Reachable only in the narrow window where a round's status still nominally
    accepts entries (SEALING) but this player's draft has already been swept
    into a submission by the sealing sweep in progress.
    """


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
    def is_committed(self) -> bool:
        return self.committed is not None


class EntryService:
    def __init__(
        self,
        rounds: RoundReader,
        drafts: DraftStore,
        submissions: SubmissionReader,
        clock: Clock,
    ) -> None:
        self._rounds = rounds
        self._drafts = drafts
        self._submissions = submissions
        self._clock = clock
        # round_id -> (expires_at, last computed snapshot). One process's
        # cache: correct as a single instance today; a second instance would
        # each keep their own 5-minute window rather than sharing one, which
        # is still a strict improvement over recomputing per request and
        # only needs revisiting if this ever runs on more than one process.
        self._standings_cache: dict[UUID, tuple[datetime, dict]] = {}

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
            raise AlreadyCommitted("entry is committed and cannot be edited")

        if prediction is not None:
            parse_slate(prediction)                    # validate before persisting
        if vote is not None:
            validate_vote(vote)
        return await self._drafts.upsert(
            round_id, user_id, prediction, vote, expected_version
        )

    async def metrics_for(self, round_id: UUID) -> dict | None:
        """Live vote standings — the coordination signal (ruleset §5).

        Sourced from drafts, not submissions: with no manual lock-in, nothing
        is a committed entry until the round seals, so the only record of "who
        has voted so far" during OPEN is what is currently drafted. A draft
        counts once it holds both a prediction and a vote — the same
        completeness bar a committed entry has always needed.

        Recomputed at most once per STANDINGS_REFRESH_SECONDS; every poll
        inside that window gets the cached snapshot. `next_refresh_at` is
        published alongside it so the client can show a real countdown
        instead of guessing when the number might change.

        Returns None during blackout and after: the dark hour serves nothing
        rather than serving something subtly different (F8).
        """
        record = await self._rounds.get(round_id)
        if record.status is not RoundStatus.OPEN:
            self._standings_cache.pop(round_id, None)
            return None

        now = self._clock.now()
        cached = self._standings_cache.get(round_id)
        if cached is not None and now < cached[0]:
            return cached[1]

        counts = [0] * 10
        total = 0
        async for chunk in self._drafts.iter_complete(round_id, 1000):
            for d in chunk:
                counts[d.vote] += 1
                total += 1

        expires_at = now + timedelta(seconds=STANDINGS_REFRESH_SECONDS)
        snapshot = {"counts": counts, "total": total, "next_refresh_at": expires_at}
        self._standings_cache[round_id] = (expires_at, snapshot)
        return snapshot
