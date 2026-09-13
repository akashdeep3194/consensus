"""services.anchor — the self-persisting round anchor.

This is the fix for the actual production incident: without it, every
process restart recomputed "midnight UTC today" from scratch whenever
ROUND_ANCHOR was unset (always true in production), so a restart landing on
a new calendar day silently collided with an already-used cycle_number
instead of ever picking a genuinely new one.
"""

import asyncio
from datetime import UTC, datetime

import pytest

from services.anchor import resolve_anchor
from tests.conftest import run


@pytest.fixture(autouse=True)
def _clean(pg_pool):
    run(pg_pool.execute("TRUNCATE schedule_anchor"))


def test_first_call_persists_the_seed(pg_pool):
    seed = datetime(2026, 1, 1, tzinfo=UTC)
    assert run(resolve_anchor(pg_pool, seed=seed)) == seed


def test_second_call_ignores_a_different_seed(pg_pool):
    """The whole point: once decided, it never moves again — not even if a
    later boot passes a different ROUND_ANCHOR."""
    first = run(resolve_anchor(pg_pool, seed=datetime(2026, 1, 1, tzinfo=UTC)))
    second = run(resolve_anchor(pg_pool, seed=datetime(2030, 6, 1, tzinfo=UTC)))
    assert second == first


def test_default_seed_is_midnight_utc_when_none_given(pg_pool):
    anchor = run(resolve_anchor(pg_pool))
    assert (anchor.hour, anchor.minute, anchor.second, anchor.microsecond) == (0, 0, 0, 0)


def test_concurrent_first_boots_converge_on_one_value(pg_pool):
    """The actual race this function exists to survive: two processes
    booting against a fresh database at the same instant must not each
    decide their own anchor."""
    async def _race():
        return await asyncio.gather(
            resolve_anchor(pg_pool, seed=datetime(2026, 1, 1, tzinfo=UTC)),
            resolve_anchor(pg_pool, seed=datetime(2030, 6, 1, tzinfo=UTC)),
        )

    a, b = run(_race())
    assert a == b
