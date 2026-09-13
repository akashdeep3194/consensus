"""Populate the currently open round so the console has live standings."""

import http.cookiejar
import json
import random
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8099"


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def call(op, method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method, headers={"Content-Type": "application/json"},
    )
    with op.open(req) as r:
        return json.loads(r.read() or "null")


def main():
    random.seed(11)
    rid = call(client(), "GET", "/api/rounds/current")["round_id"]
    # a visible bloc on 4, a smaller one on 2, the rest scattered
    for i in range(26):
        op = client()
        call(op, "POST", "/api/session", {"handle": f"rival{i:02d}"})
        vote = 4 if i < 9 else 2 if i < 15 else random.randrange(10)
        slate = "".join(map(str, random.sample(range(10), 3)))
        call(op, "PUT", f"/api/rounds/{rid}/draft", {"prediction": slate, "vote": vote})
    # No lock-in step: there is no manual commit, so a complete draft alone is
    # already enough to show up in the live standings (§5).
    st = call(client(), "GET", f"/api/rounds/{rid}/standings")
    print(f"live round seeded: {st['total']} votes cast, counts {st['counts']}")


if __name__ == "__main__":
    main()
