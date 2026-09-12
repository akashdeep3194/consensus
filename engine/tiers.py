"""Board A — The Number. Ruleset V1.1 §3.1.

Result tiers are membership-and-order, never arithmetic proximity. Digit
distance was retired in V1.1: a digit is a faction identity, not a magnitude.
"""

from collections.abc import Sequence
from enum import Enum

from engine.rank import validate_prediction


class Tier(Enum):
    """Ordered best to worst. `rank` is the sort key; `label` is player-facing."""

    TRIFECTA = (0, "TRIFECTA")
    BOXED = (1, "BOXED")
    TWO = (2, "TWO")
    ONE = (3, "ONE")
    NONE = (4, "NONE")

    def __init__(self, rank: int, label: str) -> None:
        self.rank = rank
        self.label = label

    def __lt__(self, other: "Tier") -> bool:
        return self.rank < other.rank


def tier_of(prediction: Sequence[int], winner: Sequence[int]) -> Tier:
    """Which Board A tier a prediction lands in."""
    p = validate_prediction(prediction)
    w = validate_prediction(winner)
    if p == w:
        return Tier.TRIFECTA
    overlap = len(set(p) & set(w))
    if overlap == 3:
        return Tier.BOXED  # same three digits, different order
    return {2: Tier.TWO, 1: Tier.ONE, 0: Tier.NONE}[overlap]
