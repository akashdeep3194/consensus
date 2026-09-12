"""Drive a complete round through the HTTP API: play, seal, resolve, reveal.

    python scripts/demo_round.py [base_url]

Re-runnable: handles are suffixed with a run id, so each run adds fresh players.
"""

import contextlib
import http.cookiejar
import json
import random
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8099"
RUN = str(int(time.time()))[-6:]
PLAYERS = 40
BLOC = 12          # players coordinating on digit 7
MANUAL_LOCKS = 25  # the rest are left as drafts, to be auto-committed at seal


def client():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(op, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with op.open(req) as r:
            return json.loads(r.read() or "null")
    except urllib.error.HTTPError as e:
        payload = {}
        with contextlib.suppress(Exception):
            payload = json.loads(e.read() or "{}")
        return {"__error__": e.code, "detail": payload.get("detail")}


def die(msg):
    print(f"\n  FAILED: {msg}")
    sys.exit(1)


def main():
    random.seed(7)
    rid = call(client(), "GET", "/api/rounds/current")["round_id"]
    print(f"round {rid}   (run {RUN})\n")

    players = []
    for i in range(PLAYERS):
        op = client()
        handle = f"p{RUN}_{i:02d}"
        call(op, "POST", f"/api/session?handle={handle}")
        vote = 7 if i < BLOC else random.randrange(10)
        slate = random.sample(range(10), 3)
        if i % 3 == 0:                       # some chase the visible leader
            slate = [7] + random.sample([d for d in range(10) if d != 7], 2)
        players.append((op, handle, vote, "".join(map(str, slate))))

    print("-- drafts --")
    for op, handle, vote, slate in players:
        r = call(op, "PUT", f"/api/rounds/{rid}/draft", {"prediction": slate, "vote": vote})
        if "__error__" in r:
            die(f"{handle} draft: {r}")
    print(f"  {len(players)} drafts saved")

    # optimistic concurrency: two tabs holding v1 — the second must lose
    op = players[0][0]
    first = call(op, "PUT", f"/api/rounds/{rid}/draft",
                 {"prediction": "123", "vote": 1, "version": 1})
    stale = call(op, "PUT", f"/api/rounds/{rid}/draft",
                 {"prediction": "456", "vote": 4, "version": 1})
    print(f"  first write accepted  -> v{first.get('version')}")
    print(f"  stale write rejected  -> {stale.get('__error__')} {stale.get('detail', '')[:44]}")

    print("\n-- lock-ins --")
    for op, handle, _, _ in players[:MANUAL_LOCKS]:
        r = call(op, "POST", f"/api/rounds/{rid}/lock", {"idempotency_key": f"k-{RUN}-{handle}"})
        if "__error__" in r:
            die(f"{handle} lock: {r}")
    print(f"  {MANUAL_LOCKS} locked in manually, {PLAYERS - MANUAL_LOCKS} left as drafts")

    op, handle = players[0][0], players[0][1]
    a = call(op, "POST", f"/api/rounds/{rid}/lock", {"idempotency_key": f"k-{RUN}-{handle}"})
    b = call(op, "POST", f"/api/rounds/{rid}/lock", {"idempotency_key": f"k-{RUN}-{handle}"})
    print(f"  idempotent retry -> same sequence #{a['commit_sequence']}: "
          f"{a['commit_sequence'] == b['commit_sequence']}")

    st = call(client(), "GET", f"/api/rounds/{rid}/standings")
    print("\n-- standings (live) --")
    print(f"  visible={st.get('visible')}  votes={st.get('total')}")
    print(f"  counts={st.get('counts')}")

    print("\n-- seal + resolve --")
    seal = call(client(), "POST", f"/api/admin/rounds/{rid}/seal")
    if "__error__" in seal:
        die(f"seal: {seal}")
    print(f"  auto-committed drafts : {seal['auto_committed']}")
    print(f"  total submissions     : {seal['total_submissions']}")
    print(f"  WINNING NUMBER        : {seal['winning_number']}")
    print(f"  commitment root       : {seal['commitment_root'][:40]}...")

    dark = call(client(), "GET", f"/api/rounds/{rid}/standings")
    print(f"  standings after seal  : visible={dark.get('visible')} ({dark.get('reason')})")

    res = call(client(), "GET", f"/api/rounds/{rid}/result")
    print("\n-- board A: tiers --")
    for t in res["tier_histogram"]:
        print(f"  {t['tier']:<10} {t['players']:>3}")

    print("\n-- board B: mandate, top 5 --")
    for row in res["mandate_board"][:5]:
        print(f"  #{row['rank']:<3} {row['handle']:<14} {row['prediction']}  "
              f"{row['vote_share'] * 100:>5.1f}%  {row['tier']}")

    mine = call(players[0][0], "GET", f"/api/rounds/{rid}/my-result")
    print(f"\n-- {players[0][1]}'s card --")
    print(f"  prediction {mine['prediction']} vs {mine['winning_number']} -> {mine['tier']}")
    print(f"  +{mine['points']} pts   vote {mine['vote']} finished #{mine['vote_finished']}   "
          f"slate commanded {mine['vote_share'] * 100:.1f}%")

    print("\n-- season leaderboard --")
    for i, r in enumerate(call(client(), "GET", "/api/leaderboard?limit=5"), 1):
        print(f"  {i}. {r['handle']:<14} {r['total_points']:>4} pts   "
              f"streak {r['streak']}   trifectas {r['trifectas']}")

    bad = call(players[1][0], "PUT", f"/api/rounds/{rid}/draft",
               {"prediction": "987", "vote": 9})
    print(f"\n  post-seal write rejected: {bad.get('__error__')} — {bad.get('detail')}")


if __name__ == "__main__":
    main()
