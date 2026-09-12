"""Composition root.

The one place that knows which adapters are installed. Everything else receives
ports. Swapping Postgres for something else is a change here and nowhere else.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid5

import asyncpg

from adapters.postgres import (
    PostgresDraftRepository,
    PostgresRoundRepository,
    PostgresSubmissionRepository,
)
from domain.schedule import DEFAULT_TIMING, RoundTiming
from ports.clock import SystemClock
from services.entries import EntryService
from services.rounds import RoundService
from services.sealing import SealingService

#: Namespace for deriving stable user ids from a provider subject.
USER_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def user_id_for(provider: str, external_id: str) -> UUID:
    return uuid5(USER_NAMESPACE, f"{provider}:{external_id}")


def _anchor() -> datetime:
    raw = os.environ.get("ROUND_ANCHOR")
    if raw:
        return datetime.fromisoformat(raw).astimezone(UTC)
    # default: midnight UTC today, so cycle numbers are stable across restarts
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _timing() -> RoundTiming:
    """DEMO_MINUTES compresses a 30-hour round into minutes for demos and tests."""
    minutes = os.environ.get("DEMO_ROUND_MINUTES")
    if not minutes:
        return DEFAULT_TIMING
    from datetime import timedelta

    unit = timedelta(minutes=float(minutes)) / 30       # one "hour" of the round
    return RoundTiming(
        mandate_deadline=unit * 12,
        blackout=unit * 23,
        seal=unit * 24,
        reveal=unit * 30,
        cadence=unit * 24,
    )


@dataclass
class Container:
    pool: asyncpg.Pool
    rounds: RoundService
    entries: EntryService
    sealing: SealingService
    anchor: datetime
    timing: RoundTiming

    @classmethod
    def build(cls, pool: asyncpg.Pool) -> "Container":
        clock = SystemClock()
        anchor, timing = _anchor(), _timing()
        round_repo = PostgresRoundRepository(pool)
        draft_repo = PostgresDraftRepository(pool)
        sub_repo = PostgresSubmissionRepository(pool)
        return cls(
            pool=pool,
            rounds=RoundService(round_repo, clock, anchor, timing),
            entries=EntryService(round_repo, draft_repo, sub_repo, clock),
            sealing=SealingService(round_repo, draft_repo, sub_repo, clock),
            anchor=anchor,
            timing=timing,
        )
