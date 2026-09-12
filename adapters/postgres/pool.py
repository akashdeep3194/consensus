"""Connection pool and migration runner."""

import os
import pathlib

import asyncpg

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent.parent / "db" / "migrations"


def dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "consensus")
    db = os.environ.get("PGDATABASE", "consensus")
    pw = os.environ.get("PGPASSWORD", "consensus")
    if host.startswith("/"):                       # unix socket directory
        return f"postgresql://{user}:{pw}@/{db}?host={host}&port={port}"
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


async def create_pool(min_size: int = 2, max_size: int = 20) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn(), min_size=min_size, max_size=max_size)


async def apply_migrations(pool: asyncpg.Pool) -> list[str]:
    """Apply pending migrations. Mirrors db/run_tests.sh, for app startup and tests."""
    import hashlib

    applied: list[str] = []
    async with pool.acquire() as conn:
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                 filename text PRIMARY KEY,
                 checksum text NOT NULL,
                 applied_at timestamptz NOT NULL DEFAULT now())"""
        )
        for path in sorted(MIGRATIONS.glob("*.sql")):
            body = path.read_text()
            checksum = hashlib.sha256(body.encode()).hexdigest()
            prior = await conn.fetchval(
                "SELECT checksum FROM schema_migrations WHERE filename=$1", path.name
            )
            if prior is not None:
                if prior != checksum:
                    raise RuntimeError(
                        f"{path.name} was applied with a different checksum — "
                        "never edit an applied migration"
                    )
                continue
            async with conn.transaction():
                await conn.execute(body)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename, checksum) VALUES ($1,$2)",
                    path.name,
                    checksum,
                )
            applied.append(path.name)
    return applied
