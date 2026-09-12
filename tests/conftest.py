import asyncio
import itertools
import os

import pytest

ALL_PREDICTIONS = tuple(itertools.permutations(range(10), 3))  # the 720 valid slates


def pytest_configure(config):
    config.addinivalue_line("markers", "exhaustive: full 720x720 sweep; slow")


@pytest.fixture(scope="session")
def all_predictions():
    return ALL_PREDICTIONS


# ── async test plumbing ─────────────────────────────────────────────
# One event loop for the whole session. asyncpg binds a pool to the loop that
# created it, so every coroutine in the suite must run on that same loop.

LOOP = asyncio.new_event_loop()


def run(coro):
    """Run a coroutine on the session loop."""
    return LOOP.run_until_complete(coro)


def pytest_sessionfinish(session, exitstatus):
    LOOP.close()


# ── PostgreSQL fixture ──────────────────────────────────────────────
# Tests needing a real database skip cleanly when none is configured, so the
# suite stays runnable without Docker.


def _pg_available() -> bool:
    return bool(os.environ.get("DATABASE_URL") or os.environ.get("PGHOST"))


#: Tests always get their own database. Sharing the dev one lets seeded rounds
#: and real cycle numbers leak into assertions — which they did.
TEST_DB = os.environ.get("TEST_PGDATABASE", "consensus_test")


@pytest.fixture(scope="session")
def pg_pool():
    if not _pg_available():
        pytest.skip("no database configured (set DATABASE_URL or PGHOST)")

    import asyncpg

    from adapters.postgres import apply_migrations, create_pool

    if not os.environ.get("DATABASE_URL"):
        async def _reset():
            admin = await asyncpg.connect(
                host=os.environ["PGHOST"], port=int(os.environ.get("PGPORT", 5432)),
                user=os.environ.get("PGUSER", "consensus"), database="postgres",
            )
            try:
                await admin.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
                await admin.execute(f'CREATE DATABASE "{TEST_DB}"')
            finally:
                await admin.close()

        run(_reset())
        os.environ["PGDATABASE"] = TEST_DB

    pool = run(create_pool(min_size=1, max_size=5))
    run(apply_migrations(pool))
    yield pool
    run(pool.close())
