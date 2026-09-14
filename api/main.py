"""HTTP API.

Thin by design: parse, authorise, delegate to a service, serialise. No game
rules live here — they are in engine/ and domain/.
"""

import asyncio
import contextlib
import hmac
import logging
import pathlib
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from adapters.postgres import apply_migrations, create_pool
from api.auth import get_current_user_resolver, register_auth_routes
from api.deps import Container
from api.schemas import (
    DraftIn,
    EntryOut,
    MandateRow,
    MyResultOut,
    ResultOut,
    RoundHistoryOut,
    RoundOut,
    RoundSummaryOut,
    TierCount,
)
from domain.lifecycle import RoundStatus
from engine import InvalidPrediction, InvalidVote
from ports.repositories import ConcurrentModification, RoundClosed, RoundNotFound
from services.entries import AlreadyCommitted
from services.rounds import RoundView
from services.scheduler import run_scheduler, sweep_once
from services.scoring import award

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("consensus")

WEB = pathlib.Path(__file__).resolve().parent.parent / "web"
container: Container | None = None


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global container
    pool = await create_pool()
    applied = await apply_migrations(pool)
    if applied:
        log.info("applied migrations: %s", ", ".join(applied))
    container = await Container.build(pool)
    await _ensure_current_round()

    # The background scheduler (services.scheduler): sleeps exactly until the
    # next round boundary and sweeps, independent of whether anyone happens
    # to be visiting right then. Cancelled cleanly on shutdown below.
    scheduler_task = asyncio.create_task(run_scheduler(C))
    yield
    scheduler_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await scheduler_task
    await container.aclose()


app = FastAPI(title="Consensus 3D", version="1.1.0", lifespan=lifespan)


def C() -> Container:
    if container is None:
        raise HTTPException(503, "starting up")
    return container


# ── auth ───────────────────────────────────────────────────────────────────
# Real identity (services.auth, api.auth): Google OAuth mints the same signed
# session cookie dev sign-in does, so nothing downstream of `current_user`
# ever needs to know which one a player used.

current_user = get_current_user_resolver(C)
register_auth_routes(app, C)


# ── rounds ─────────────────────────────────────────────────────────────────


async def _ensure_current_round():
    await C().rounds.ensure_current()


def _round_out(view: RoundView) -> RoundOut:
    return RoundOut(**{k: getattr(view, k) for k in RoundOut.model_fields})


@app.get("/api/rounds/current", response_model=RoundOut)
async def current_round():
    await _ensure_current_round()
    record = await C().rounds.current()
    if record is None:
        live = await C().rounds.live()
        if not live:
            raise HTTPException(404, "no live round")
        record = live[-1]
    return _round_out(RoundView.of(record, datetime.now(UTC)))


@app.get("/api/rounds", response_model=list[RoundOut])
async def list_rounds():
    await _ensure_current_round()
    now = datetime.now(UTC)
    return [_round_out(RoundView.of(r, now)) for r in await C().rounds.live()]


@app.get("/api/rounds/history", response_model=RoundHistoryOut)
async def round_history(before_cycle: int | None = None, limit: int = Query(20, ge=1, le=100)):
    """Past rounds with a real result, newest first — the History tab.

    Public, like `result()` below: this is round-wide metadata, not anything
    personal to the caller. Never 404s — no rounds yet is a valid, empty page.
    """
    page = await C().rounds.history(before_cycle, limit)
    return RoundHistoryOut(
        rounds=[
            RoundSummaryOut(
                round_id=r.round_id,
                cycle_number=r.cycle_number,
                opens_at=r.schedule.opens_at,
                reveals_at=r.schedule.reveals_at,
                winning_number=r.winning_number,
                commitment_root=r.commitment_root,
            )
            for r in page.rounds
        ],
        next_before_cycle=page.next_before_cycle,
    )


@app.get("/api/rounds/latest-revealed")
async def latest_revealed():
    """The most recently revealed round.

    Players come back to see how they did, and the current round is already a
    different one — so the console needs this to show the last result next to
    the live game.
    """
    row = await C().pool.fetchrow(
        """SELECT round_id FROM rounds WHERE status='revealed'
           ORDER BY cycle_number DESC LIMIT 1"""
    )
    if row is None:
        raise HTTPException(404, "nothing revealed yet")
    return {"round_id": str(row["round_id"])}


@app.get("/api/rounds/{round_id}/standings")
async def standings(round_id: UUID):
    """Live vote distribution — the coordination signal. Dark during blackout."""
    try:
        metrics = await C().entries.metrics_for(round_id)
    except RoundNotFound as exc:
        raise HTTPException(404, "round not found") from exc
    if metrics is None:
        return {"visible": False, "reason": "blackout"}
    return {"visible": True, **metrics}


# ── entries ────────────────────────────────────────────────────────────────


@app.get("/api/rounds/{round_id}/entry", response_model=EntryOut)
async def my_entry(round_id: UUID, user_id: UUID = Depends(current_user)):  # noqa: B008
    state = await C().entries.state(round_id, user_id)
    if state.committed:
        e = state.committed
        return EntryOut(
            committed=True, prediction=e.prediction, vote=e.vote,
            commit_sequence=e.commit_sequence, mandate_eligible=e.mandate_eligible,
            committed_at=e.committed_at,
        )
    if state.draft:
        d = state.draft
        return EntryOut(
            committed=False, prediction=d.prediction, vote=d.vote,
            version=d.version, updated_at=d.updated_at,
        )
    return EntryOut(committed=False)


@app.put("/api/rounds/{round_id}/draft", response_model=EntryOut)
async def save_draft(
    round_id: UUID, body: DraftIn, user_id: UUID = Depends(current_user)  # noqa: B008
):
    try:
        draft = await C().entries.save_draft(
            round_id, user_id, body.prediction, body.vote, body.version
        )
    except RoundNotFound as exc:
        raise HTTPException(404, "round not found") from exc
    except RoundClosed as exc:
        raise HTTPException(409, str(exc)) from exc
    except AlreadyCommitted as exc:
        raise HTTPException(409, str(exc)) from exc
    except ConcurrentModification as exc:
        raise HTTPException(409, f"{exc} — reload and try again") from exc
    except (InvalidPrediction, InvalidVote) as exc:
        raise HTTPException(422, str(exc)) from exc
    return EntryOut(
        committed=False, prediction=draft.prediction, vote=draft.vote,
        version=draft.version, updated_at=draft.updated_at,
    )


# ── results ────────────────────────────────────────────────────────────────


async def _result_for(round_id: UUID):
    record = await C().rounds._rounds.get(round_id)  # noqa: SLF001
    if record.status not in (RoundStatus.SEALED, RoundStatus.RESOLVING, RoundStatus.REVEALED):
        raise HTTPException(409, f"round is {record.status}; no result yet")
    return await C().sealing.resolve_round(round_id, persist=False)


@app.get("/api/rounds/{round_id}/result", response_model=ResultOut)
async def result(round_id: UUID):
    r = await _result_for(round_id)
    board = r.mandate_board[:50]
    handles = await _handles({p.user_id for p in board})
    return ResultOut(
        round_id=round_id,
        winning_number="".join(str(d) for d in r.winning_number),
        counts=list(r.counts),
        total_votes=r.total_votes,
        full_ranking=list(r.full_ranking),
        tier_histogram=[
            TierCount(tier=t.label, players=n) for t, n in r.tier_histogram.items() if n
        ],
        commitment_root=r.commitment_root,
        algorithm_version=r.algorithm_version,
        mandate_board=[
            MandateRow(
                rank=p.mandate_rank,
                handle=handles.get(p.user_id, "anonymous"),
                prediction="".join(str(d) for d in p.prediction),
                mandate_score=p.mandate_score,
                vote_share=float(p.vote_share),
                tier=p.tier.label,
            )
            for p in board
        ],
    )


async def _handles(user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    handles = await C().users.get_handles([UUID(u) for u in user_ids])
    return {str(uid): h for uid, h in handles.items()}


@app.get("/api/rounds/{round_id}/my-result", response_model=MyResultOut)
async def my_result(round_id: UUID, user_id: UUID = Depends(current_user)):  # noqa: B008
    r = await _result_for(round_id)
    mine = next((p for p in r.players if p.user_id == str(user_id)), None)
    if mine is None:
        raise HTTPException(404, "you did not enter this round")

    recorded = await _recorded(user_id, round_id)
    if recorded is None:
        streak_now = await C().pool.fetchval(
            "SELECT streak FROM user_seasons WHERE user_id=$1", user_id
        ) or 0
        points, streak = award(mine.tier, streak_now)
    else:
        points, streak = recorded
    finished = r.full_ranking.index(mine.vote) + 1
    return MyResultOut(
        round_id=round_id,
        winning_number="".join(str(d) for d in r.winning_number),
        prediction="".join(str(d) for d in mine.prediction),
        vote=mine.vote,
        tier=mine.tier.label,
        points=points,
        streak=streak,
        mandate_score=mine.mandate_score,
        mandate_rank=mine.mandate_rank,
        vote_share=float(mine.vote_share),
        vote_finished=finished,
    )


async def _recorded(user_id: UUID, round_id: UUID) -> tuple[int, int] | None:
    """(points, streak_after) as recorded at reveal, if the round is scored."""
    row = await C().pool.fetchrow(
        "SELECT points, streak_after FROM round_results WHERE round_id=$1 AND user_id=$2",
        round_id, user_id,
    )
    return (row["points"], row["streak_after"]) if row else None


# ── operations ─────────────────────────────────────────────────────────────
# These can force a round to seal before its real deadline, which changes who
# wins — every route below requires the operator token (api.deps.Container.
# admin_token), skipped only in DEV_LOGIN=1 (local runs, tests, the demo
# scripts), where it is never even reachable in the first place.


async def require_admin(authorization: str | None = Header(None)) -> None:
    c = C()
    if c.dev_login_enabled:
        return
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, c.admin_token):
        raise HTTPException(401, "invalid admin token")


@app.post("/api/admin/advance", dependencies=[Depends(require_admin)])
async def advance():
    """Run the scheduler sweep now — the exact code the background loop runs
    on its own timer (services.scheduler), exposed for ops and tests so
    neither has to wait for it."""
    result = await sweep_once(C())
    return {
        "moved": [{"round": str(a), "from": b, "to": c} for a, b, c in result.moved],
        "sealed": [str(s) for s in result.sealed],
        "finalized": [str(s) for s in result.finalized],
    }


@app.post("/api/admin/rounds/{round_id}/seal", dependencies=[Depends(require_admin)])
async def force_seal(round_id: UUID):
    """Seal and resolve a round now, regardless of the clock.

    An operator action, used by demos and tests. It does not bypass any rule —
    it runs the same sealing-and-finalizing path the scheduler would
    (services.sealing.SealingService.seal / .finalize), so auto-commit, the
    commitment root and resolution all behave identically. `finalize` returns
    None on a round that was already finalized by the time this runs (e.g. the
    background scheduler beat this call to it) — the plain recompute is still
    correct there, just not something to persist twice.
    """
    report = await C().sealing.seal(round_id)
    result = await C().sealing.finalize(round_id) or await C().sealing.resolve_round(
        round_id, persist=False
    )
    # Sealing early leaves a gap the schedule would not fill until the next
    # cycle is due, so a force-seal opens the successor immediately — the
    # same self-healing ensure_current() already runs on every request and
    # every scheduler sweep (services.rounds.RoundService.ensure_open_round).
    # In normal operation the daily overlap (Q3) means a round is always
    # live and this is a no-op.
    next_round = await C().rounds.ensure_open_round()
    return {
        "round_id": str(round_id),
        "next_round_id": str(next_round.round_id) if next_round else None,
        "auto_committed": report.drafts_committed,
        "total_submissions": report.total_submissions,
        "winning_number": "".join(str(d) for d in result.winning_number),
        "commitment_root": result.commitment_root,
    }


@app.get("/api/leaderboard")
async def leaderboard(limit: int = 20):
    rows = await C().pool.fetch(
        """SELECT COALESCE(u.handle, u.external_id) AS handle,
                  s.total_points, s.streak, s.best_streak,
                  s.trifectas, s.boxed, s.rounds_played
           FROM user_seasons s JOIN users u USING (user_id)
           ORDER BY s.total_points DESC, s.best_streak DESC LIMIT $1""",
        limit,
    )
    return [dict(r) for r in rows]


@app.get("/api/me/season")
async def my_season(user_id: UUID = Depends(current_user)):  # noqa: B008
    """The running total behind the topbar's points chip and its popup.

    A player who has never been scored yet has no user_seasons row at all —
    that is a real zero, not a missing record, so it returns the zeroed
    shape rather than 404ing.
    """
    row = await C().pool.fetchrow(
        """SELECT total_points, streak, best_streak, trifectas, boxed, rounds_played,
                  (SELECT count(*) + 1 FROM user_seasons
                     WHERE total_points > s.total_points) AS rank
           FROM user_seasons s WHERE user_id = $1""",
        user_id,
    )
    if row is None:
        return {
            "total_points": 0, "streak": 0, "best_streak": 0,
            "trifectas": 0, "boxed": 0, "rounds_played": 0, "rank": None,
        }
    return dict(row)


@app.get("/api/me/results")
async def my_results(round_ids: str, user_id: UUID = Depends(current_user)):  # noqa: B008
    """Which of these rounds the caller has a scored result for, and what it
    was — the batched lookup the History list uses to show an outcome per
    row without one request per round. A round missing from the response is
    simply one the caller never entered, not an error.
    """
    # cap matches /api/rounds/history's own page-size ceiling
    try:
        ids = [UUID(r) for r in round_ids.split(",") if r][:100]
    except ValueError as exc:
        raise HTTPException(422, f"malformed round_id: {exc}") from exc
    rows = await C().pool.fetch(
        """SELECT round_id, tier, points FROM round_results
           WHERE user_id = $1 AND round_id = ANY($2::uuid[])""",
        user_id, ids,
    )
    return [dict(r) for r in rows]


@app.get("/api/health")
async def health():
    await C().pool.fetchval("SELECT 1")
    return {"ok": True, "version": app.version}


# ── static console ─────────────────────────────────────────────────────────
# No build step, no hashed/versioned filenames — every JS/CSS file is served
# at the same URL forever, so without an explicit Cache-Control a browser's
# own heuristic freshness guess is what decides whether it ever notices a
# deploy. `no-cache` doesn't stop caching — it just forces a revalidation
# round-trip (If-None-Match) on every load, a cheap 304 when nothing changed
# and an actual fresh copy the moment something did, deploy or not.


class RevalidatedStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["cache-control"] = "no-cache"
        return response


app.mount("/static", RevalidatedStaticFiles(directory=WEB / "static"), name="static")


@app.get("/")
async def console():
    return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})
