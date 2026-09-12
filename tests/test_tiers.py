"""Board A — ruleset V1.1 §3.1."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine import Tier, tier_of

pred_st = st.lists(st.integers(0, 9), min_size=3, max_size=3, unique=True).map(tuple)


@pytest.mark.parametrize(
    "prediction,expected",
    [
        ((5, 2, 7), Tier.TRIFECTA),
        ((7, 2, 5), Tier.BOXED),
        ((2, 5, 7), Tier.BOXED),
        ((5, 2, 1), Tier.TWO),
        ((5, 1, 3), Tier.ONE),
        ((1, 3, 4), Tier.NONE),
    ],
)
def test_tiers_against_winner_527(prediction, expected):
    assert tier_of(prediction, (5, 2, 7)) is expected


def test_all_six_permutations_are_trifecta_or_boxed():
    import itertools

    w = (5, 2, 7)
    tiers = [tier_of(p, w) for p in itertools.permutations(w)]
    assert tiers.count(Tier.TRIFECTA) == 1
    assert tiers.count(Tier.BOXED) == 5


@given(pred_st, pred_st)
def test_tier_is_total_and_symmetric_in_membership(p, w):
    t = tier_of(p, w)
    assert t in Tier
    # BOXED and TRIFECTA both mean full overlap
    assert (len(set(p) & set(w)) == 3) == (t in (Tier.TRIFECTA, Tier.BOXED))


@given(pred_st)
def test_prediction_equals_winner_is_always_trifecta(p):
    assert tier_of(p, p) is Tier.TRIFECTA


def test_tier_ordering_is_best_first():
    assert Tier.TRIFECTA < Tier.BOXED < Tier.TWO < Tier.ONE < Tier.NONE
