"""Season scoring — what a win is actually worth.

Board A tiers convert to points; consecutive rounds with a Trifecta or Boxed
build a streak multiplier. Deliberately not money: no payments, no custody, no
regulatory surface.
"""

from engine import Tier

POINTS: dict[Tier, int] = {
    Tier.TRIFECTA: 100,
    Tier.BOXED: 50,
    Tier.TWO: 10,
    Tier.ONE: 2,
    Tier.NONE: 0,
}

#: Tiers that extend a streak.
STREAK_TIERS = frozenset({Tier.TRIFECTA, Tier.BOXED})

MAX_STREAK_MULTIPLIER = 3.0


def streak_multiplier(streak: int) -> float:
    """1.0 at no streak, +0.25 per consecutive hit, capped at 3x."""
    if streak <= 1:
        return 1.0
    return min(1.0 + 0.25 * (streak - 1), MAX_STREAK_MULTIPLIER)


def award(tier: Tier, streak_before: int) -> tuple[int, int]:
    """Return (points, streak_after) for a result."""
    extends = tier in STREAK_TIERS
    streak_after = streak_before + 1 if extends else 0
    base = POINTS[tier]
    if base == 0:
        return 0, streak_after
    return round(base * streak_multiplier(streak_after)), streak_after
