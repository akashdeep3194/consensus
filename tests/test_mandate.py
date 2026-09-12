"""Board B — ruleset V1.1 §3.2. The three properties that justify the weighting."""

import itertools
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine import mandate_score, vote_share, winning_number
from engine.mandate import WEIGHTS

counts_st = st.lists(st.integers(min_value=0, max_value=10**5), min_size=10, max_size=10)
ALL = tuple(itertools.permutations(range(10), 3))


def test_weights_are_three_two_one():
    assert WEIGHTS == (3, 2, 1)


# ── property 1: the maximum is uniquely the Trifecta ────────────────
@settings(max_examples=150)
@given(counts_st)
def test_maximum_is_the_winning_number(counts):
    best = max(ALL, key=lambda p: mandate_score(p, counts))
    assert mandate_score(best, counts) == mandate_score(winning_number(counts), counts)


@settings(max_examples=60)
@given(st.lists(st.integers(1, 10**5), min_size=10, max_size=10, unique=True))
def test_maximum_is_unique_when_counts_are_distinct(counts):
    w = winning_number(counts)
    top = mandate_score(w, counts)
    assert [p for p in ALL if mandate_score(p, counts) == top] == [w]


# ── property 2: misordering costs exactly the vote margin ───────────
@settings(max_examples=150)
@given(counts_st)
def test_swap_cost_equals_the_margin_between_those_digits(counts):
    w = winning_number(counts)
    a, b, c = w
    # swapping positions 1 and 2 costs (3-2)*C[a] - (3-2)*C[b] = C[a] - C[b]
    assert mandate_score(w, counts) - mandate_score((b, a, c), counts) == (
        counts[a] - counts[b]
    )
    # swapping positions 2 and 3 costs C[b] - C[c]
    assert mandate_score(w, counts) - mandate_score((a, c, b), counts) == (
        counts[b] - counts[c]
    )


def test_swap_cost_worked_example():
    counts = [24_000] * 10
    counts[7], counts[3], counts[8] = 175_000, 125_000, 25_000
    w = winning_number(counts)
    assert w == (7, 3, 8)
    assert mandate_score(w, counts) == 800_000
    assert mandate_score((7, 8, 3), counts) == 700_000        # cost 100_000
    assert mandate_score(w, counts) - mandate_score((7, 8, 3), counts) == (
        counts[3] - counts[8]
    )


# ── property 3: it ranks finely, unlike unweighted summation ────────
@pytest.mark.parametrize(
    "counts",
    [
        [1, 2, 4, 8, 16, 32, 64, 128, 256, 512],            # no coincidental collisions
        [100_000, 92_000, 81_000, 73_000, 64_000, 55_000, 47_000, 38_000, 26_000, 11_000],
        [24_000] * 7 + [175_000, 125_000, 25_000],
    ],
)
def test_unweighted_summation_is_capped_at_120_ranks(counts):
    """Order-blind scoring can never exceed one rank per digit SET: C(10,3) = 120."""
    raw = {sum(counts[d] for d in p) for p in ALL}
    weighted = {mandate_score(p, counts) for p in ALL}
    assert len(raw) <= 120
    assert len(weighted) > len(raw)     # weighting always separates strictly further


def test_weighting_separates_far_beyond_the_unweighted_cap():
    """On a count vector free of coincidental collisions, weighting clears the cap."""
    counts = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512]
    assert len({sum(counts[d] for d in p) for p in ALL}) == 120     # exactly at the cap
    assert len({mandate_score(p, counts) for p in ALL}) == 429      # 3.5x finer


def test_unweighted_would_tie_every_permutation():
    counts = [24_000] * 10
    counts[7], counts[3], counts[8] = 175_000, 125_000, 25_000
    perms = list(itertools.permutations((7, 3, 8)))
    assert len({sum(counts[d] for d in p) for p in perms}) == 1
    assert len({mandate_score(p, counts) for p in perms}) == 6


# ── the documented conflict that forces two boards ──────────────────
def test_weighted_score_does_not_respect_tier_order():
    """Ruleset §3.3: partial hits can outscore the worst BOXED permutation."""
    counts = [24_000] * 10
    counts[7], counts[3], counts[8] = 175_000, 125_000, 25_000
    w = winning_number(counts)
    worst_boxed = min(
        (p for p in itertools.permutations(w) if p != w), key=lambda p: mandate_score(p, counts)
    )
    floor = mandate_score(worst_boxed, counts)
    beating = [
        p for p in ALL if len(set(p) & set(w)) == 2 and mandate_score(p, counts) > floor
    ]
    assert len(beating) == 49


# ── vote share ──────────────────────────────────────────────────────
def test_vote_share_is_exact():
    counts = [10] * 10
    assert vote_share((1, 2, 3), counts) == Fraction(3, 10)


def test_vote_share_of_empty_round_is_zero():
    assert vote_share((1, 2, 3), [0] * 10) == Fraction(0)


@settings(max_examples=100)
@given(counts_st)
def test_vote_share_is_order_blind_and_bounded(counts):
    for p in [(1, 2, 3), (3, 2, 1), (2, 1, 3)]:
        assert vote_share(p, counts) == vote_share((1, 2, 3), counts)
    assert Fraction(0) <= vote_share((1, 2, 3), counts) <= Fraction(1)


@pytest.mark.parametrize("bad", [(1, 1, 2), (1, 2), (1, 2, 10)])
def test_rejects_invalid_predictions(bad):
    from engine import InvalidPrediction

    with pytest.raises(InvalidPrediction):
        mandate_score(bad, [0] * 10)
