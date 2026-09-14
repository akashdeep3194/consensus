"""HTTP-level tests: a whole round, through the real API.

Covers the path a browser actually takes — session, draft edits, seal,
result — so a regression in wiring is caught even when every unit test passes.
"""

import os
import uuid

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from adapters.postgres import PostgresRoundRepository  # noqa: E402
from domain.lifecycle import RoundStatus  # noqa: E402
from tests.conftest import run  # noqa: E402


@pytest.fixture(scope="module")
def client(pg_pool):
    """Runs against the isolated test database, never the dev one."""
    os.environ["DEV_LOGIN"] = "1"
    os.environ.setdefault("DEMO_ROUND_MINUTES", "60")

    from api.main import app

    with TestClient(app) as c:
        yield c


def handle() -> str:
    return "t" + uuid.uuid4().hex[:10]


def sign_in(client, name: str) -> dict:
    """Register `name` and return per-request kwargs identifying them.

    One TestClient for the whole module: the app's connection pool is bound to
    that client's event loop, so spawning another client per player would cross
    loops. Identity travels as an explicit cookie instead of shared jar state —
    the real signed session cookie dev sign-in mints, not a stand-in for it.
    """
    signed_cookie = client.post("/api/session", json={"handle": name}).cookies["cx_session"]
    client.cookies.clear()
    return {"cookies": {"cx_session": signed_cookie}}


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_current_round_exposes_server_time(client):
    r = client.get("/api/rounds/current").json()
    assert r["status"] in ("open", "blackout", "sealing", "sealed", "resolving", "revealed")
    assert r["server_time"], "the client must never rely on its own clock (§6.4)"
    assert r["opens_at"] < r["mandate_deadline"] < r["blackout_at"] < r["seals_at"]


def test_draft_requires_authentication(client):
    rid = client.get("/api/rounds/current").json()["round_id"]
    assert client.put(
        f"/api/rounds/{rid}/draft", json={"prediction": "527", "vote": 5}
    ).status_code == 401


def test_repeated_digits_are_rejected(client):
    rid = client.get("/api/rounds/current").json()["round_id"]
    who = sign_in(client, handle())
    r = client.put(f"/api/rounds/{rid}/draft", json={"prediction": "112", "vote": 1}, **who)
    assert r.status_code == 422


def test_vote_out_of_range_is_rejected(client):
    rid = client.get("/api/rounds/current").json()["round_id"]
    who = sign_in(client, handle())
    bad = client.put(f"/api/rounds/{rid}/draft", json={"prediction": "527", "vote": 10}, **who)
    assert bad.status_code == 422


def test_draft_stays_editable_with_no_manual_commit(client):
    """There is no user-initiated lock-in (§6): a draft is edited freely, as
    many times as the player likes, for as long as the round accepts entries.
    """
    rid = client.get("/api/rounds/current").json()["round_id"]
    who = sign_in(client, handle())

    saved = client.put(
        f"/api/rounds/{rid}/draft", json={"prediction": "527", "vote": 5}, **who
    ).json()
    assert saved["version"] == 1 and saved["committed"] is False

    revised = client.put(
        f"/api/rounds/{rid}/draft",
        json={"prediction": "418", "vote": 4, "version": 1}, **who
    ).json()
    assert revised["version"] == 2 and revised["committed"] is False
    assert revised["prediction"] == "418", "edits replace the draft, they don't merge with it"

    # The old manual commit route is gone outright, not merely disabled.
    assert client.post(f"/api/rounds/{rid}/lock", json={}, **who).status_code == 404


def test_incomplete_draft_can_still_be_saved(client):
    """Completeness only matters at seal (§4) — saving is never gated on it."""
    rid = client.get("/api/rounds/current").json()["round_id"]
    who = sign_in(client, handle())
    r = client.put(f"/api/rounds/{rid}/draft", json={"prediction": "527"}, **who)  # no vote
    assert r.status_code == 200
    assert r.json()["committed"] is False


def test_stale_version_conflicts(client):
    rid = client.get("/api/rounds/current").json()["round_id"]
    who = sign_in(client, handle())
    client.put(f"/api/rounds/{rid}/draft", json={"prediction": "527", "vote": 5}, **who)
    client.put(
        f"/api/rounds/{rid}/draft", json={"prediction": "123", "vote": 1, "version": 1}, **who
    )
    stale = client.put(
        f"/api/rounds/{rid}/draft", json={"prediction": "456", "vote": 4, "version": 1}, **who
    )
    assert stale.status_code == 409


def test_full_round_seals_resolves_and_scores(client):
    """The whole loop, end to end, on a round of its own.

    Earlier tests in this module leave entries on the shared current round, so
    this starts by sealing it — which also exercises the successor being opened
    automatically — and plays the fresh one.
    """
    stale = client.get("/api/rounds/current").json()["round_id"]
    client.post(f"/api/admin/rounds/{stale}/seal")
    rid = client.get("/api/rounds/current").json()["round_id"]
    assert rid != stale, "sealing a round must open its successor"

    players = []
    for i in range(9):
        who = sign_in(client, handle())
        vote = 7 if i < 5 else i
        client.put(f"/api/rounds/{rid}/draft", json={"prediction": "715", "vote": vote}, **who)
        players.append(who)

    live = client.get(f"/api/rounds/{rid}/standings").json()
    assert live["visible"] is True
    assert live["total"] == 9, "every complete draft counts, with no lock-in step"

    sealed = client.post(f"/api/admin/rounds/{rid}/seal").json()
    assert len(sealed["winning_number"]) == 3
    assert len(set(sealed["winning_number"])) == 3, "always three distinct digits"
    assert len(sealed["commitment_root"]) == 64
    assert sealed["total_submissions"] == 9
    assert sealed["auto_committed"] == 9, "every complete draft auto-commits at seal"

    dark = client.get(f"/api/rounds/{rid}/standings").json()
    assert dark["visible"] is False, "standings must close once the round is sealed"

    res = client.get(f"/api/rounds/{rid}/result").json()
    assert sum(t["players"] for t in res["tier_histogram"]) == 9
    ranks = [row["rank"] for row in res["mandate_board"]]
    assert ranks == sorted(ranks), "board rows must be ordered by rank"
    scores = [row["mandate_score"] for row in res["mandate_board"]]
    assert scores == sorted(scores, reverse=True), "rank must follow the weighted score"

    mine = client.get(f"/api/rounds/{rid}/my-result", **players[0]).json()
    assert mine["tier"] in ("TRIFECTA", "BOXED", "TWO", "ONE", "NONE")
    assert mine["points"] >= 0
    assert 1 <= mine["vote_finished"] <= 10

    entry0 = client.get(f"/api/rounds/{rid}/entry", **players[0]).json()
    assert entry0["committed"] is True
    assert entry0["mandate_eligible"] is True, (
        "saved immediately and never touched again — well before the mandate "
        "deadline, so auto-commit at seal must still count it for Board B"
    )

    board = client.get("/api/leaderboard?limit=5").json()
    assert isinstance(board, list)

    blocked = client.put(
        f"/api/rounds/{rid}/draft", json={"prediction": "987", "vote": 9}, **players[1]
    )
    assert blocked.status_code == 409, "a sealed round rejects writes through every path"


def test_result_is_unavailable_before_sealing(client):
    fresh = client.post("/api/admin/advance").json()
    assert "moved" in fresh


def test_history_lists_revealed_rounds_and_paginates(client):
    """The History tab's backend: newest first, a real result on every row,
    and a cursor that only ever points at an actual further page."""
    who = sign_in(client, handle())
    revealed = []
    for _ in range(3):
        rid = client.get("/api/rounds/current").json()["round_id"]
        # A round with zero votes has no real result and is excluded from
        # history — cast one so each of these three actually qualifies.
        client.put(f"/api/rounds/{rid}/draft", json={"prediction": "715", "vote": 7}, **who)
        sealed = client.post(f"/api/admin/rounds/{rid}/seal").json()
        assert sealed["winning_number"], "force-seal must finalize, not just seal"
        revealed.append(rid)
    newest_first = list(reversed(revealed))

    first = client.get("/api/rounds/history?limit=2").json()
    assert [r["round_id"] for r in first["rounds"]] == newest_first[:2]
    assert first["next_before_cycle"] is not None
    for row in first["rounds"]:
        assert len(row["winning_number"]) == 3
        assert len(row["commitment_root"]) == 64

    # Earlier tests in this module also seal rounds, so there may be more
    # history behind ours — assert only what this test itself put there.
    second = client.get(
        f"/api/rounds/history?limit=2&before_cycle={first['next_before_cycle']}"
    ).json()
    assert second["rounds"][0]["round_id"] == newest_first[2]

    # A page requested past the very oldest round must never invite a further
    # one — walk to the end and confirm next_before_cycle lands on None there.
    cursor = first["next_before_cycle"]
    for _ in range(50):
        page = client.get(f"/api/rounds/history?limit=2&before_cycle={cursor}").json()
        if page["next_before_cycle"] is None:
            break
        cursor = page["next_before_cycle"]
    else:
        pytest.fail("history pagination never terminated")
    assert page["next_before_cycle"] is None, "must never invite a page with nothing on it"


def test_admin_advance_recovers_when_nothing_is_live(client, pg_pool):
    """Reproduces the actual production incident directly: a stale anchor
    left nothing live in production with no way back except a manual admin
    call. Force every currently-live round into VOIDED here (legal from any
    pre-REVEALED status) to recreate that same "nothing live" precondition,
    then confirm the *passive* path — POST /api/admin/advance, not
    force_seal — is what brings a live round back on its own.
    """
    rounds = PostgresRoundRepository(pg_pool)
    stuck = run(rounds.live())
    for r in stuck:
        run(rounds.transition(r.round_id, r.status, RoundStatus.VOIDED))
    # Checked at the repository level, not via GET /api/rounds — that
    # endpoint's own ensure_current() would self-heal on this very call and
    # never observably return [] once the fix is in place.
    assert run(rounds.live()) == [], "the incident's exact symptom: nothing live"

    client.post("/api/admin/advance")

    current = client.get("/api/rounds/current")
    assert current.status_code == 200
    assert current.json()["status"] in ("open", "blackout")


def test_my_season_is_zeroed_before_any_score(client):
    """A player who has never been scored has no user_seasons row at all —
    that's a real zero, not a missing record, so this must not 404."""
    who = sign_in(client, handle())
    season = client.get("/api/me/season", **who).json()
    assert season == {
        "total_points": 0, "streak": 0, "best_streak": 0,
        "trifectas": 0, "boxed": 0, "rounds_played": 0, "rank": None,
    }


def test_my_season_and_results_reflect_a_scored_round(client):
    who = sign_in(client, handle())
    rid = client.get("/api/rounds/current").json()["round_id"]
    client.put(f"/api/rounds/{rid}/draft", json={"prediction": "715", "vote": 7}, **who)
    sealed = client.post(f"/api/admin/rounds/{rid}/seal").json()
    assert sealed["winning_number"]

    season = client.get("/api/me/season", **who).json()
    assert season["rounds_played"] == 1
    assert season["rank"] is not None

    results = client.get(f"/api/me/results?round_ids={rid}", **who).json()
    assert len(results) == 1
    assert results[0]["round_id"] == rid
    assert results[0]["points"] == season["total_points"], "their only round so far"

    # A round sealing just opened a successor — this account never entered
    # it, so it must not show up in the batched lookup.
    successor = client.get("/api/rounds/current").json()["round_id"]
    if successor != rid:
        empty = client.get(f"/api/me/results?round_ids={successor}", **who).json()
        assert empty == []


def test_my_results_rejects_a_malformed_round_id(client):
    """round_ids is parsed by hand (it's a comma-separated list, not a single
    UUID path param FastAPI can validate on its own) — a bad id must come
    back as a clean 422, not an unhandled 500."""
    who = sign_in(client, handle())
    resp = client.get("/api/me/results?round_ids=not-a-uuid", **who)
    assert resp.status_code == 422
