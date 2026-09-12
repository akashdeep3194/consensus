"""The full 720 x 720 sweep. M1 exit criterion."""

import itertools

import pytest

from engine import Tier, tier_of

ALL = tuple(itertools.permutations(range(10), 3))


def test_prediction_space_is_exactly_720():
    assert len(ALL) == 720
    assert len(set(ALL)) == 720


@pytest.mark.exhaustive
def test_every_prediction_against_every_winner():
    """All 518,400 pairs resolve to a valid tier, with exact tier counts per winner."""
    pairs = 0
    for w in ALL:
        hist = dict.fromkeys(Tier, 0)
        for p in ALL:
            hist[tier_of(p, w)] += 1
            pairs += 1
        # exactly one exact hit, five reorderings of the same three digits
        assert hist[Tier.TRIFECTA] == 1, w
        assert hist[Tier.BOXED] == 5, w
        # choose 2 of the 3 winning digits, 1 of the other 7, times 3! orderings
        assert hist[Tier.TWO] == 3 * 7 * 6, w
        assert hist[Tier.ONE] == 3 * 21 * 6, w
        assert hist[Tier.NONE] == 35 * 6, w
        assert sum(hist.values()) == 720, w
    assert pairs == 720 * 720


@pytest.mark.exhaustive
def test_tier_partitions_the_space_for_a_sample_winner():
    w = (5, 2, 7)
    groups = {t: [p for p in ALL if tier_of(p, w) is t] for t in Tier}
    assert sum(len(v) for v in groups.values()) == 720
    assert groups[Tier.TRIFECTA] == [w]
    assert set(groups[Tier.BOXED]) == set(itertools.permutations(w)) - {w}
