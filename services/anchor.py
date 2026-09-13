"""The round anchor: cycle 0's opening instant, persisted once.

A plain function taking a raw pool, not a Protocol in ports/repositories.py —
this is a singleton config value read once per process lifetime, the same
shape of concern as services/results.py's record_results, not a per-entity
repository.
"""

from datetime import UTC, datetime

import asyncpg


async def resolve_anchor(pool: asyncpg.Pool, seed: datetime | None = None) -> datetime:
    """The persisted anchor, creating it from `seed` on a database's first boot.

    Every boot after the first is one indexed read. Only a boot that finds
    the table empty attempts the insert, and INSERT ... ON CONFLICT DO
    NOTHING against the singleton primary key means at most one insert ever
    commits: Postgres resolves a concurrent conflict by blocking the loser
    on the winner's row lock, so by the time the loser's own re-read below
    runs, the winner's value is already committed and visible.
    """
    existing = await pool.fetchval("SELECT anchor FROM schedule_anchor WHERE id")
    if existing is not None:
        return existing

    chosen = seed if seed is not None else (
        datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    )
    await pool.execute(
        "INSERT INTO schedule_anchor (id, anchor) VALUES (true, $1) "
        "ON CONFLICT (id) DO NOTHING",
        chosen,
    )
    return await pool.fetchval("SELECT anchor FROM schedule_anchor WHERE id")
