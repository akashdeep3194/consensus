"""Composition root.

The one place that knows which adapters are installed, and the one place
environment variables are read for anything security-relevant. Everything
else receives typed values or ports — swapping an adapter, or tightening a
default, is a change here and nowhere else.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import asyncpg
import httpx

from adapters.auth import GoogleOAuthProvider, ItsDangerousSessionSigner
from adapters.postgres import (
    PostgresDraftRepository,
    PostgresRoundRepository,
    PostgresSubmissionRepository,
    PostgresUserRepository,
)
from domain.schedule import DEFAULT_TIMING, RoundTiming
from ports.auth import SessionSigner, UserRepository, user_id_for
from ports.clock import SystemClock
from services.auth import AuthService
from services.entries import EntryService
from services.rounds import RoundService
from services.sealing import SealingService

#: Re-exported for compatibility with existing tests and scripts
USER_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

__all__ = ["Container", "USER_NAMESPACE", "user_id_for"]


def _anchor() -> datetime:
    raw = os.environ.get("ROUND_ANCHOR")
    if raw:
        return datetime.fromisoformat(raw).astimezone(UTC)
    # default: midnight UTC today, so cycle numbers are stable across restarts
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def _timing() -> RoundTiming:
    """DEMO_MINUTES compresses a 24-hour round into minutes for demos and tests."""
    minutes = os.environ.get("DEMO_ROUND_MINUTES")
    if not minutes:
        return DEFAULT_TIMING
    from datetime import timedelta

    unit = timedelta(minutes=float(minutes)) / 24       # one "hour" of the round
    return RoundTiming(
        mandate_deadline=unit * 12,
        blackout=unit * 23,
        seal=unit * 23.5,
        reveal=unit * 24,
        cadence=unit * 24,
    )


@dataclass
class Container:
    pool: asyncpg.Pool
    rounds: RoundService
    entries: EntryService
    sealing: SealingService
    users: UserRepository
    auth: AuthService
    signer: SessionSigner
    anchor: datetime
    timing: RoundTiming
    dev_login_enabled: bool
    admin_token: str
    _http_client: httpx.AsyncClient

    @classmethod
    def build(cls, pool: asyncpg.Pool) -> "Container":
        clock = SystemClock()
        anchor, timing = _anchor(), _timing()
        round_repo = PostgresRoundRepository(pool)
        draft_repo = PostgresDraftRepository(pool)
        sub_repo = PostgresSubmissionRepository(pool)
        user_repo = PostgresUserRepository(pool)

        # DEV_LOGIN=1 is the one flag that only ever comes from scripts/dev.sh
        # or a deliberately-configured test run — never a deployed default —
        # so it is the single signal that relaxes anything security-relevant
        # below. Forgetting to set it is what a real deployment looks like.
        dev_login_enabled = os.environ.get("DEV_LOGIN") == "1"

        secret_key = os.environ.get("SESSION_SECRET")
        if not secret_key:
            if not dev_login_enabled:
                raise RuntimeError(
                    "SESSION_SECRET is required unless DEV_LOGIN=1. Refusing to "
                    "start and sign sessions with a key that is public in this "
                    "repository's history."
                )
            secret_key = "consensus-insecure-dev-session-key-change-in-prod"
        signer = ItsDangerousSessionSigner(secret_key=secret_key)

        # The admin endpoints can force a round to seal before its real
        # deadline, which changes who wins — every bit as security-relevant
        # as the session key, and held to the same fail-closed rule.
        admin_token = os.environ.get("ADMIN_TOKEN")
        if not admin_token:
            if not dev_login_enabled:
                raise RuntimeError(
                    "ADMIN_TOKEN is required unless DEV_LOGIN=1. Refusing to start "
                    "with the round-control endpoints open to anyone on the internet."
                )
            # Never actually compared: require_admin skips the check entirely
            # whenever dev_login_enabled is true. This only keeps the field a
            # plain str rather than str | None.
            admin_token = "consensus-insecure-dev-admin-token"

        # One shared client for every Google token/userinfo call, rather than a
        # fresh TLS handshake per sign-in; closed by Container.aclose().
        http_client = httpx.AsyncClient()

        providers = []
        google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
        google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        if google_client_id and google_client_secret:
            providers.append(
                GoogleOAuthProvider(
                    client_id=google_client_id,
                    client_secret=google_client_secret,
                    http_client=http_client,
                )
            )

        auth = AuthService(user_repo=user_repo, signer=signer, providers=providers)

        return cls(
            pool=pool,
            rounds=RoundService(round_repo, clock, anchor, timing),
            entries=EntryService(round_repo, draft_repo, sub_repo, clock),
            sealing=SealingService(round_repo, draft_repo, sub_repo, clock),
            users=user_repo,
            auth=auth,
            signer=signer,
            anchor=anchor,
            timing=timing,
            dev_login_enabled=dev_login_enabled,
            admin_token=admin_token,
            _http_client=http_client,
        )

    async def aclose(self) -> None:
        await self._http_client.aclose()
        await self.pool.close()
