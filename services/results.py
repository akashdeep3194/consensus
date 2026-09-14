"""Persisting a resolved round's outcome.

Round results are derived data (§ engine/resolve.py) — recomputable from the
committed submission set at any time, so a failure here never threatens the
authoritative record. That's also why this takes a raw pool rather than a
port: it is a reporting/rollup concern, not core game state, so it sits beside
services/scoring.py's pure point math rather than behind ports/repositories.py
alongside rounds, drafts and submissions.
"""

from uuid import UUID

import asyncpg

from engine import Tier
from engine.resolve import RoundResult
from services.scoring import award


async def record_results(pool: asyncpg.Pool, round_id: UUID, result: RoundResult) -> None:
    """Persist per-player outcomes and roll up season totals.

    Safe to call more than once for the same round — required now that
    finalisation is automatic and retried every sweep rather than a single
    manual admin action (services.sealing.SealingService.finalize): a crash
    between finishing this round and the caller learning about it means a
    later retry must not double-score anyone. `round_results` is the record
    of whether a given user was already scored for this round — the
    `RETURNING` clause tells us whether *this* call is the one that inserted
    it, and the `user_seasons` rollup is only ever applied when it was, so a
    repeat call for an already-recorded player is a true no-op rather than a
    second helping of points onto their season.
    """
    async with pool.acquire() as conn, conn.transaction():
        # Sorted by user_id: two rounds are deliberately live at once
        # (services/rounds.py's daily overlap), so two finalize() calls can
        # genuinely run at the same instant. FOR UPDATE below makes each
        # player's streak read-then-write atomic against that; locking in a
        # fixed order across both transactions is what keeps two such calls
        # sharing players from deadlocking on each other's locks.
        for p in sorted(result.players, key=lambda p: p.user_id):
            uid = UUID(p.user_id)
            # Seeded first so FOR UPDATE always has a row to lock — without
            # this, a player's very first-ever scored round has no season
            # row yet, and the lock below protects nothing.
            await conn.execute(
                """INSERT INTO user_seasons (user_id,total_points,streak,best_streak,
                       trifectas,boxed,rounds_played)
                   VALUES ($1,0,0,0,0,0,0)
                   ON CONFLICT (user_id) DO NOTHING""",
                uid,
            )
            streak_before = await conn.fetchval(
                "SELECT streak FROM user_seasons WHERE user_id=$1 FOR UPDATE", uid
            ) or 0
            points, streak_after = award(p.tier, streak_before)
            inserted = await conn.fetchval(
                """INSERT INTO round_results (round_id,user_id,tier,points,streak_after,
                       mandate_score,mandate_rank)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)
                   ON CONFLICT (round_id,user_id) DO NOTHING
                   RETURNING round_id""",
                round_id, uid, p.tier.label, points, streak_after,
                p.mandate_score, p.mandate_rank,
            )
            if inserted is None:
                continue                    # already scored by an earlier call
            await conn.execute(
                """INSERT INTO user_seasons (user_id,total_points,streak,best_streak,
                       trifectas,boxed,rounds_played)
                   VALUES ($1,$2,$3,$3,$4,$5,1)
                   ON CONFLICT (user_id) DO UPDATE SET
                     total_points = user_seasons.total_points + EXCLUDED.total_points,
                     streak       = EXCLUDED.streak,
                     best_streak  = greatest(user_seasons.best_streak, EXCLUDED.streak),
                     trifectas    = user_seasons.trifectas + EXCLUDED.trifectas,
                     boxed        = user_seasons.boxed + EXCLUDED.boxed,
                     rounds_played= user_seasons.rounds_played + 1,
                     updated_at   = now()""",
                uid, points, streak_after,
                1 if p.tier is Tier.TRIFECTA else 0,
                1 if p.tier is Tier.BOXED else 0,
            )
