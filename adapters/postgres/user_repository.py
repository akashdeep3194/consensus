"""PostgreSQL implementation of UserRepository."""

from collections.abc import Sequence
from uuid import UUID, uuid4

import asyncpg

from ports.auth import MAX_HANDLE_SUFFIX_ATTEMPTS, UserRecord

_COLUMNS = "user_id, external_id, provider, COALESCE(handle, external_id) AS handle, email"


def _record(row: asyncpg.Record) -> UserRecord:
    return UserRecord(
        user_id=row["user_id"],
        external_id=row["external_id"],
        provider=row["provider"],
        handle=row["handle"],
        email=row["email"],
    )


class PostgresUserRepository:
    """Stores and retrieves user profiles from PostgreSQL."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_by_id(self, user_id: UUID) -> UserRecord | None:
        row = await self._pool.fetchrow(
            f"SELECT {_COLUMNS} FROM users WHERE user_id = $1", user_id
        )
        return _record(row) if row else None

    async def get_by_external(self, provider: str, external_id: str) -> UserRecord | None:
        row = await self._pool.fetchrow(
            f"SELECT {_COLUMNS} FROM users WHERE provider = $1 AND external_id = $2",
            provider, external_id,
        )
        return _record(row) if row else None

    async def ensure_user(
        self,
        user_id: UUID,
        external_id: str,
        provider: str,
        handle: str,
        email: str | None = None,
    ) -> UserRecord:
        # Fast path: this account already exists. Its handle is never touched
        # again; its email refreshes to whatever the provider offers now.
        existing = await self._pool.fetchrow(
            f"""UPDATE users SET email = COALESCE($3, email)
                WHERE provider = $1 AND external_id = $2
                RETURNING {_COLUMNS}""",
            provider, external_id, email,
        )
        if existing is not None:
            return _record(existing)

        # Brand-new account: claim `handle`, or the first free variant of it.
        # A conflict here is either the handle belonging to a *different*
        # account (try the next variant) or a concurrent sign-in that beat us
        # to creating *this* one (their row is now authoritative) — checking
        # whether the account exists yet tells the two apart without having
        # to name which unique constraint fired.
        candidates = [handle, *(f"{handle}{n}" for n in range(2, MAX_HANDLE_SUFFIX_ATTEMPTS))]
        candidates.append(f"{handle}-{uuid4().hex[:6]}")  # last resort, ~guaranteed free
        for attempt in candidates:
            try:
                row = await self._pool.fetchrow(
                    f"""INSERT INTO users (user_id, external_id, provider, handle, email)
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING {_COLUMNS}""",
                    user_id, external_id, provider, attempt, email,
                )
                return _record(row)
            except asyncpg.UniqueViolationError:
                winner = await self.get_by_external(provider, external_id)
                if winner is not None:
                    return winner
                continue  # `attempt` was someone else's handle — try the next one

        raise RuntimeError(f"could not provision a user row for {provider}:{external_id}")

    async def get_handles(self, user_ids: Sequence[UUID]) -> dict[UUID, str]:
        if not user_ids:
            return {}
        rows = await self._pool.fetch(
            """SELECT user_id, COALESCE(handle, external_id) AS handle
               FROM users WHERE user_id = ANY($1::uuid[])""",
            list(user_ids),
        )
        return {r["user_id"]: r["handle"] for r in rows}
