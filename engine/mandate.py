"""Board B — The Mandate. Ruleset V1.1 §3.2.

    mandate_score(P) = 3*C[P1] + 2*C[P2] + 1*C[P3]

Position-weighted so that the board ranks finely (~670 of 720 ranks, against
120 for unweighted summation, which is order-blind) and so that the cost of
misordering two positions is exactly the vote margin between those digits.

By the rearrangement inequality the maximum is attained uniquely by the true
winning number in exact order.
"""

from collections.abc import Sequence
from fractions import Fraction

from engine.rank import validate_counts, validate_prediction

WEIGHTS = (3, 2, 1)


def mandate_score(prediction: Sequence[int], counts: Sequence[int]) -> int:
    """Position-weighted vote total. Integer arithmetic."""
    p = validate_prediction(prediction)
    c = validate_counts(counts)
    return sum(w * c[d] for w, d in zip(WEIGHTS, p, strict=True))


def vote_share(prediction: Sequence[int], counts: Sequence[int]) -> Fraction:
    """Share of all votes the player's three digits commanded — the displayed number.

    Exact rational, so the caller decides rounding. Zero votes gives 0.
    """
    p = validate_prediction(prediction)
    c = validate_counts(counts)
    total = sum(c)
    if total == 0:
        return Fraction(0)
    return Fraction(sum(c[d] for d in p), total)
