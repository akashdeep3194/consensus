"""PostgreSQL adapters.

Explicit SQL rather than an ORM: this surface is small and every statement is
correctness-critical, so each one should be readable in full.

These satisfy exactly the same port protocols as the in-memory adapters and are
exercised by the same conformance suite.
"""

from collections.abc import AsyncIterator, Sequence
from uuid import UUID, uuid4

import asyncpg

from domain.lifecycle import RoundStatus, require_legal
from domain.schedule import RoundSchedule
from ports.repositories import (
    CommittedEntry,
    ConcurrentModification,
    Draft,
    RoundClosed,
    RoundNotFound,
    RoundRecord,
)

ROUND_COLUMNS = """
  round_id, cycle_number, status, opens_at, mandate_deadline, blackout_at,
  seals_at, reveals_at, ruleset_version, algorithm_version,
  commitment_root, winning_number
"""


def _round(row: asyncpg.Record) -> RoundRecord:
    return RoundRecord(
        round_id=row["round_id"],
        cycle_number=row["cycle_number"],
        status=RoundStatus(row["status"]),
        schedule=RoundSchedule(
            cycle_number=row["cycle_number"],
            opens_at=row["opens_at"],
            mandate_deadline=row["mandate_deadline"],
            blackout_at=row["blackout_at"],
            seals_at=row["seals_at"],
            reveals_at=row["reveals_at"],
        ),
        ruleset_version=row["ruleset_version"],
        algorithm_version=row["algorithm_version"],
        commitment_root=row["commitment_root"],
        winning_number=row["winning_number"],
    )


def _draft(row: asyncpg.Record) -> Draft:
    return Draft(
        round_id=row["round_id"],
        user_id=row["user_id"],
        prediction=row["prediction"],
        vote=row["vote"],
        version=row["version"],
        updated_at=row["updated_at"],
    )


def _entry(row: asyncpg.Record) -> CommittedEntry:
    return CommittedEntry(
        submission_id=row["submission_id"],
        round_id=row["round_id"],
        user_id=row["user_id"],
        prediction=row["prediction"],
        vote=row["vote"],
        commit_sequence=row["commit_sequence"],
        committed_at=row["committed_at"],
        mandate_eligible=row["mandate_eligible"],
        voided_at=row["voided_at"],
    )


def _translate(exc: asyncpg.PostgresError) -> Exception:
    """Map database errors onto the port contract.

    The triggers raise with ERRCODE check_violation, which asyncpg surfaces as
    CheckViolationError — not RaiseError. Callers must never see a driver type,
    so translation happens here at the boundary and nowhere else.
    """
    message = str(exc)
    if "no longer accepts entries" in message:
        return RoundClosed(message)
    if "does not exist" in message:
        return RoundNotFound(message)
    return exc


class PostgresRoundRepository:
    """Satisfies RoundReader and RoundWriter."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, record: RoundRecord) -> None:
        s = record.schedule
        try:
            await self._pool.execute(
                """INSERT INTO rounds (round_id, cycle_number, status, opens_at,
                       mandate_deadline, blackout_at, seals_at, reveals_at,
                       ruleset_version, algorithm_version)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                record.round_id, record.cycle_number, record.status.value,
                s.opens_at, s.mandate_deadline, s.blackout_at, s.seals_at,
                s.reveals_at, record.ruleset_version, record.algorithm_version,
            )
        except asyncpg.UniqueViolationError as exc:
            raise ValueError(f"cycle_number {record.cycle_number} already exists") from exc

    async def get(self, round_id: UUID) -> RoundRecord:
        row = await self._pool.fetchrow(
            f"SELECT {ROUND_COLUMNS} FROM rounds WHERE round_id=$1", round_id
        )
        if row is None:
            raise RoundNotFound(str(round_id))
        return _round(row)

    async def by_cycle(self, cycle_number: int) -> RoundRecord | None:
        row = await self._pool.fetchrow(
            f"SELECT {ROUND_COLUMNS} FROM rounds WHERE cycle_number=$1", cycle_number
        )
        return _round(row) if row else None

    async def live(self) -> Sequence[RoundRecord]:
        rows = await self._pool.fetch(
            f"""SELECT {ROUND_COLUMNS} FROM rounds
                WHERE status NOT IN ('revealed','voided')
                ORDER BY cycle_number"""
        )
        return [_round(r) for r in rows]

    async def history(
        self, before_cycle: int | None, limit: int
    ) -> Sequence[RoundRecord]:
        # A round nobody voted in has no real result — see RoundReader.history's
        # docstring — so it's excluded here too, before LIMIT ever applies.
        where = (
            "status='revealed' AND winning_number IS NOT NULL AND EXISTS "
            "(SELECT 1 FROM submissions s WHERE s.round_id = rounds.round_id "
            "AND s.voided_at IS NULL)"
        )
        if before_cycle is None:
            rows = await self._pool.fetch(
                f"SELECT {ROUND_COLUMNS} FROM rounds WHERE {where} "
                f"ORDER BY cycle_number DESC LIMIT $1",
                limit,
            )
        else:
            rows = await self._pool.fetch(
                f"SELECT {ROUND_COLUMNS} FROM rounds WHERE {where} "
                f"AND cycle_number < $2 ORDER BY cycle_number DESC LIMIT $1",
                limit, before_cycle,
            )
        return [_round(r) for r in rows]

    async def highest_cycle(self) -> int:
        return await self._pool.fetchval("SELECT coalesce(max(cycle_number),-1) FROM rounds")

    async def transition(
        self, round_id: UUID, expected: RoundStatus, to: RoundStatus
    ) -> RoundRecord:
        # Fail fast on an illegal edge so callers get the domain error rather
        # than a database exception; the trigger is still the real backstop.
        require_legal(expected, to)
        row = await self._pool.fetchrow(
            f"""UPDATE rounds SET status=$3
                WHERE round_id=$1 AND status=$2
                RETURNING {ROUND_COLUMNS}""",
            round_id, expected.value, to.value,
        )
        if row is None:
            current = await self.get(round_id)      # raises RoundNotFound if absent
            raise ConcurrentModification(
                f"round {round_id} is {current.status}, expected {expected}"
            )
        return _round(row)

    async def seal_with_root(self, round_id: UUID, commitment_root: str) -> RoundRecord:
        """SEALING -> SEALED plus the commitment, in one statement.

        The `root_requires_sealed` constraint rejects a root on a round that is
        not yet sealed, which is correct: while materialisation is still running
        the input set is not final. Doing both in one UPDATE satisfies it and
        removes the window where a sealed round has no commitment.
        """
        row = await self._pool.fetchrow(
            f"""UPDATE rounds
                SET status='sealed', commitment_root=$2, committed_at_seal=now()
                WHERE round_id=$1 AND status='sealing'
                RETURNING {ROUND_COLUMNS}""",
            round_id, commitment_root,
        )
        if row is None:
            current = await self.get(round_id)
            raise ConcurrentModification(
                f"round {round_id} is {current.status}, expected sealing"
            )
        return _round(row)

    async def record_resolution(self, round_id: UUID, winning_number: str) -> None:
        await self._pool.execute(
            "UPDATE rounds SET winning_number=$2, resolved_at=now() WHERE round_id=$1",
            round_id, winning_number,
        )


class PostgresDraftRepository:
    """Satisfies DraftRepository and DraftScanner."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, round_id: UUID, user_id: UUID) -> Draft | None:
        row = await self._pool.fetchrow(
            """SELECT round_id,user_id,prediction,vote,version,updated_at
               FROM round_drafts WHERE round_id=$1 AND user_id=$2""",
            round_id, user_id,
        )
        return _draft(row) if row else None

    async def upsert(
        self,
        round_id: UUID,
        user_id: UUID,
        prediction: str | None,
        vote: int | None,
        expected_version: int | None,
    ) -> Draft:
        try:
            if expected_version is None:
                row = await self._pool.fetchrow(
                    """INSERT INTO round_drafts (round_id,user_id,prediction,vote)
                       VALUES ($1,$2,$3,$4)
                       ON CONFLICT DO NOTHING
                       RETURNING round_id,user_id,prediction,vote,version,updated_at""",
                    round_id, user_id, prediction, vote,
                )
                if row is None:
                    raise ConcurrentModification(
                        f"draft already exists for user {user_id} in round {round_id}"
                    )
                return _draft(row)

            row = await self._pool.fetchrow(
                """UPDATE round_drafts
                   SET prediction=$3, vote=$4, version=version+1
                   WHERE round_id=$1 AND user_id=$2 AND version=$5
                   RETURNING round_id,user_id,prediction,vote,version,updated_at""",
                round_id, user_id, prediction, vote, expected_version,
            )
            if row is None:
                raise ConcurrentModification(
                    f"draft version mismatch for user {user_id}: caller had {expected_version}"
                )
            return _draft(row)
        except asyncpg.PostgresError as exc:
            raise _translate(exc) from exc

    async def delete(self, round_id: UUID, user_id: UUID) -> None:
        await self._pool.execute(
            "DELETE FROM round_drafts WHERE round_id=$1 AND user_id=$2", round_id, user_id
        )

    async def iter_complete(
        self, round_id: UUID, chunk_size: int
    ) -> AsyncIterator[Sequence[Draft]]:
        """Keyset pagination in the canonical seal order (F4).

        Ordered by (updated_at, user_id) so an auditor replaying the round
        derives the same commit_sequence values we did.
        """
        cursor: tuple | None = None
        while True:
            if cursor is None:
                rows = await self._pool.fetch(
                    """SELECT round_id,user_id,prediction,vote,version,updated_at
                       FROM round_drafts
                       WHERE round_id=$1 AND is_complete
                       ORDER BY updated_at, user_id
                       LIMIT $2""",
                    round_id, chunk_size,
                )
            else:
                rows = await self._pool.fetch(
                    """SELECT round_id,user_id,prediction,vote,version,updated_at
                       FROM round_drafts
                       WHERE round_id=$1 AND is_complete
                         AND (updated_at, user_id) > ($2, $3)
                       ORDER BY updated_at, user_id
                       LIMIT $4""",
                    round_id, cursor[0], cursor[1], chunk_size,
                )
            if not rows:
                return
            yield [_draft(r) for r in rows]
            cursor = (rows[-1]["updated_at"], rows[-1]["user_id"])
            if len(rows) < chunk_size:
                return

    async def count_complete(self, round_id: UUID) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM round_drafts WHERE round_id=$1 AND is_complete", round_id
        )


class PostgresSubmissionRepository:
    """Satisfies SubmissionReader and SubmissionWriter."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_for_user(self, round_id: UUID, user_id: UUID) -> CommittedEntry | None:
        row = await self._pool.fetchrow(
            """SELECT submission_id,round_id,user_id,prediction,vote,commit_sequence,
                      committed_at,mandate_eligible,voided_at
               FROM submissions WHERE round_id=$1 AND user_id=$2""",
            round_id, user_id,
        )
        return _entry(row) if row else None

    async def commit_entry(
        self,
        round_id: UUID,
        user_id: UUID,
        prediction: str,
        vote: int,
        mandate_eligible: bool,
        idempotency_key: str | None = None,
    ) -> CommittedEntry:
        """Lock in one entry, transactionally (§5.1).

        commit_sequence is allocated inside the transaction from the round's own
        max, so it is dense and unique per round. The unique constraint is the
        backstop if two transactions race.
        """
        async with self._pool.acquire() as conn, conn.transaction():
            if idempotency_key is not None:
                prior = await conn.fetchrow(
                    """SELECT submission_id,round_id,user_id,prediction,vote,
                              commit_sequence,committed_at,mandate_eligible,voided_at
                       FROM submissions
                       WHERE round_id=$1 AND user_id=$2 AND idempotency_key=$3""",
                    round_id, user_id, idempotency_key,
                )
                if prior is not None:
                    return _entry(prior)

            # serialise sequence allocation for this round only
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(round_id))
            seq = await conn.fetchval(
                "SELECT coalesce(max(commit_sequence),0)+1 FROM submissions WHERE round_id=$1",
                round_id,
            )
            try:
                row = await conn.fetchrow(
                    """INSERT INTO submissions (submission_id,round_id,user_id,prediction,
                           vote,commit_sequence,source,mandate_eligible,idempotency_key)
                       VALUES ($1,$2,$3,$4,$5,$6,'manual',$7,$8)
                       RETURNING submission_id,round_id,user_id,prediction,vote,
                                 commit_sequence,committed_at,mandate_eligible,voided_at""",
                    uuid4(), round_id, user_id, prediction, vote, seq,
                    mandate_eligible, idempotency_key,
                )
            except asyncpg.UniqueViolationError as exc:
                raise ConcurrentModification(
                    f"user {user_id} already has an entry in round {round_id}"
                ) from exc
            except asyncpg.PostgresError as exc:
                raise _translate(exc) from exc
            return _entry(row)

    async def iter_round(
        self, round_id: UUID, chunk_size: int
    ) -> AsyncIterator[Sequence[CommittedEntry]]:
        after = 0
        while True:
            rows = await self._pool.fetch(
                """SELECT submission_id,round_id,user_id,prediction,vote,commit_sequence,
                          committed_at,mandate_eligible,voided_at
                   FROM submissions
                   WHERE round_id=$1 AND commit_sequence > $2
                   ORDER BY commit_sequence
                   LIMIT $3""",
                round_id, after, chunk_size,
            )
            if not rows:
                return
            yield [_entry(r) for r in rows]
            after = rows[-1]["commit_sequence"]

    async def count(self, round_id: UUID) -> int:
        return await self._pool.fetchval(
            "SELECT count(*) FROM submissions WHERE round_id=$1", round_id
        )
