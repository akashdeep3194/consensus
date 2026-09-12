"""HTTP-level tests: a whole round, through the real API.

Covers the path a browser actually takes — session, draft, lock-in, seal,
result — so a regression in wiring is caught even when every unit test passes.
"""

import os
import uuid

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(request):
    if not (os.environ.get("DATABASE_URL") or os.environ.get("PGHOST")):
        pytest.skip("no database configured")
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
    loops. Identity travels as an explicit cookie instead of shared jar state.
    """
    client.post(f"/api/session?handle={name}")
    client.cookies.clear()
    return {"cookies": {"cx_user": name}}


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


def test_draft_then_lock_then_immutable(client):
    rid = client.get("/api/rounds/current").json()["round_id"]
    who = sign_in(client, handle())

    saved = client.put(
        f"/api/rounds/{rid}/draft", json={"prediction": "527", "vote": 5}, **who
    ).json()
    assert saved["version"] == 1 and saved["locked"] is False

    locked = client.post(f"/api/rounds/{rid}/lock", json={"idempotency_key": "k1"}, **who).json()
    assert locked["locked"] is True and locked["commit_sequence"] >= 1

    again = client.post(f"/api/rounds/{rid}/lock", json={"idempotency_key": "k1"}, **who).json()
    assert again["commit_sequence"] == locked["commit_sequence"], "retry must not duplicate"

    after = client.put(f"/api/rounds/{rid}/draft", json={"prediction": "123", "vote": 1}, **who)
    assert after.status_code == 409, "a committed entry can never be edited (§1.3)"


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


def test_lock_without_a_complete_draft_is_rejected(client):
    rid = client.get("/api/rounds/current").json()["round_id"]
    who = sign_in(client, handle())
    client.put(f"/api/rounds/{rid}/draft", json={"prediction": "527"}, **who)     # no vote
    assert client.post(f"/api/rounds/{rid}/lock", json={}, **who).status_code == 422


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
        if i % 2 == 0:
            client.post(f"/api/rounds/{rid}/lock", json={"idempotency_key": f"e{i}"}, **who)
        players.append(who)

    live = client.get(f"/api/rounds/{rid}/standings").json()
    assert live["visible"] is True

    sealed = client.post(f"/api/admin/rounds/{rid}/seal").json()
    assert len(sealed["winning_number"]) == 3
    assert len(set(sealed["winning_number"])) == 3, "always three distinct digits"
    assert len(sealed["commitment_root"]) == 64
    assert sealed["total_submissions"] == 9, "incomplete drafts auto-commit at seal"

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

    board = client.get("/api/leaderboard?limit=5").json()
    assert isinstance(board, list)

    blocked = client.put(
        f"/api/rounds/{rid}/draft", json={"prediction": "987", "vote": 9}, **players[1]
    )
    assert blocked.status_code == 409, "a sealed round rejects writes through every path"


def test_result_is_unavailable_before_sealing(client):
    fresh = client.post("/api/admin/advance").json()
    assert "moved" in fresh
