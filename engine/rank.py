"""Outcome engine — ruleset V1.1 §2.

    The winning number is the three most-voted digits, ranked by vote count.
    Ties resolve to the lower digit.

Integer comparison only: no division, no rational arithmetic, no float. The
result is a pure function of the count vector.
"""

from collections.abc import Sequence

from engine.errors import InvalidCounts, InvalidPrediction, InvalidVote

DIGITS = range(10)
POSITIONS = 3


def validate_counts(counts: Sequence[int]) -> tuple[int, ...]:
    """Return counts as a canonical tuple, or raise InvalidCounts."""
    if len(counts) != 10:
        raise InvalidCounts(f"expected 10 counts, got {len(counts)}")
    out = []
    for d, c in enumerate(counts):
        # bool is an int subclass; reject it so True never silently means 1
        if not isinstance(c, int) or isinstance(c, bool):
            raise InvalidCounts(f"count for digit {d} is not an int: {c!r}")
        if c < 0:
            raise InvalidCounts(f"count for digit {d} is negative: {c}")
        out.append(c)
    return tuple(out)


def validate_vote(vote: int) -> int:
    if not isinstance(vote, int) or isinstance(vote, bool) or not 0 <= vote <= 9:
        raise InvalidVote(f"vote must be a digit 0-9, got {vote!r}")
    return vote


def validate_prediction(prediction: Sequence[int]) -> tuple[int, int, int]:
    """Predictions are three DISTINCT digits, ordered. 720 are valid."""
    p = tuple(prediction)
    if len(p) != POSITIONS:
        raise InvalidPrediction(f"prediction must have {POSITIONS} digits, got {len(p)}")
    for d in p:
        if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 9:
            raise InvalidPrediction(f"prediction digit out of range: {d!r}")
    if len(set(p)) != POSITIONS:
        raise InvalidPrediction(f"prediction digits must be distinct: {p}")
    return p


def winning_number(counts: Sequence[int]) -> tuple[int, int, int]:
    """counts[0..9] -> the winning number as three distinct digits.

    Sort key is (-count, digit): count descending, then digit ascending so equal
    counts always resolve to the lower digit. With every count zero the whole
    vector ties and the result is (0, 1, 2) with no special case.
    """
    c = validate_counts(counts)
    ranked = sorted(DIGITS, key=lambda d: (-c[d], d))
    return tuple(ranked[:POSITIONS])  # type: ignore[return-value]


def full_ranking(counts: Sequence[int]) -> tuple[int, ...]:
    """All ten digits in outcome order. Used by the audit ledger for runner-up data."""
    c = validate_counts(counts)
    return tuple(sorted(DIGITS, key=lambda d: (-c[d], d)))
