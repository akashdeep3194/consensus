"""Regenerate tests/golden_vectors.json.

Run ONLY when a rule change is intended, and bump ALGORITHM_VERSION first.
    make golden
"""

import json
import pathlib

from engine import Submission, resolve
from engine.version import ALGORITHM_VERSION, RULESET_VERSION

PATH = pathlib.Path(__file__).parent / "golden_vectors.json"

CASES = [
    ("empty-round", []),
    ("ruleset-example-903", [(9, (9, 0, 3)), (9, (0, 9, 3)), (0, (1, 2, 3)), (3, (5, 6, 7))]),
    ("tie-to-lower-digit", [(5, (5, 2, 7)), (2, (2, 5, 7)), (5, (1, 2, 3)), (2, (4, 5, 6))]),
    ("all-same-vote", [(7, (7, 1, 2)), (7, (1, 7, 2)), (7, (3, 4, 5))]),
    ("every-digit-once", [(d, (d, (d + 1) % 10, (d + 2) % 10)) for d in range(10)]),
    ("single-entry", [(4, (4, 0, 1))]),
]


def build(name, entries):
    subs = [
        Submission(
            round_id=name[:64],
            submission_id=f"s{i:03d}",
            user_id=f"u{i:03d}",
            prediction=p,
            vote=v,
            commit_sequence=i,
            mandate_eligible=(i % 2 == 0),
        )
        for i, (v, p) in enumerate(entries)
    ]
    r = resolve(name[:64], subs)
    return {
        "name": name,
        "entries": [{"vote": v, "prediction": list(p)} for v, p in entries],
        "winning_number": list(r.winning_number),
        "counts": list(r.counts),
        "full_ranking": list(r.full_ranking),
        "tier_histogram": {t.label: n for t, n in r.tier_histogram.items()},
        "mandate_board": [
            {"submission_id": p.submission_id, "score": p.mandate_score, "rank": p.mandate_rank}
            for p in r.mandate_board
        ],
        "audit": [
            {
                "position": a.position, "digit": a.digit, "votes": a.votes,
                "runner_up_digit": a.runner_up_digit, "margin": a.margin,
                "decided_by_tie_break": a.decided_by_tie_break,
            }
            for a in r.audit
        ],
        "commitment_root": r.commitment_root,
    }


def main():
    doc = {
        "ruleset_version": RULESET_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "note": "Frozen expected output. Changing these requires an ALGORITHM_VERSION bump.",
        "cases": [build(n, e) for n, e in CASES],
    }
    PATH.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"wrote {PATH} — {len(doc['cases'])} cases at algorithm_version {ALGORITHM_VERSION}")


if __name__ == "__main__":
    main()
