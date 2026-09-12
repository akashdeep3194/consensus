"""Outcome engine — ruleset V1.1 §2."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine import InvalidCounts, InvalidPrediction, InvalidVote
from engine.rank import full_ranking, validate_prediction, validate_vote, winning_number

counts_st = st.lists(st.integers(min_value=0, max_value=10**6), min_size=10, max_size=10)


def c(**kw):
    a = [0] * 10
    for k, v in kw.items():
        a[int(k[1:])] = v
    return a


# ── worked examples from docs/00-ruleset.md §2 ──────────────────────
@pytest.mark.parametrize(
    "counts,expected",
    [
        (c(d9=500, d0=400, d3=300), (9, 0, 3)),
        (c(d5=100, d2=100, d7=50), (2, 5, 7)),   # 2 and 5 tie -> lower digit first
        ([0] * 10, (0, 1, 2)),                    # every count ties
    ],
)
def test_ruleset_examples(counts, expected):
    assert winning_number(counts) == expected


def test_zero_votes_needs_no_special_case():
    assert winning_number([0] * 10) == (0, 1, 2)


def test_tie_break_is_lower_digit_at_every_position():
    assert winning_number([7] * 10) == (0, 1, 2)
    # 4 and 6 tie below 9; the lower must take the earlier position
    assert winning_number(c(d9=10, d6=5, d4=5)) == (9, 4, 6)


# ── properties ──────────────────────────────────────────────────────
@given(counts_st)
def test_always_three_distinct_digits(counts):
    w = winning_number(counts)
    assert len(w) == 3
    assert len(set(w)) == 3
    assert all(0 <= d <= 9 for d in w)


@given(counts_st)
def test_deterministic(counts):
    assert winning_number(counts) == winning_number(list(counts))


@given(counts_st)
def test_counts_are_weakly_descending_along_the_result(counts):
    w = winning_number(counts)
    assert counts[w[0]] >= counts[w[1]] >= counts[w[2]]


@given(counts_st)
def test_winner_digits_beat_every_excluded_digit(counts):
    """No excluded digit may have a strictly higher count than any winner."""
    w = winning_number(counts)
    for d in range(10):
        if d not in w:
            for wd in w:
                assert (counts[wd], -wd) >= (counts[d], -d)


@given(counts_st)
def test_full_ranking_is_a_permutation_starting_with_the_winner(counts):
    r = full_ranking(counts)
    assert sorted(r) == list(range(10))
    assert r[:3] == winning_number(counts)


@settings(max_examples=200)
@given(st.permutations(range(10)), st.integers(min_value=0, max_value=500))
def test_vote_arrival_order_is_irrelevant(order, n):
    """Only the count vector matters, never who voted when."""
    counts = [0] * 10
    for i, d in enumerate(order):
        counts[d] = (i * 7 + n) % 23
    assert winning_number(counts) == winning_number(tuple(counts))


# ── validation ──────────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [[0] * 9, [0] * 11, [], [1] * 10 + [1]])
def test_rejects_wrong_length(bad):
    with pytest.raises(InvalidCounts):
        winning_number(bad)


def test_rejects_negative_and_non_int_counts():
    with pytest.raises(InvalidCounts):
        winning_number([-1] + [0] * 9)
    with pytest.raises(InvalidCounts):
        winning_number([1.5] + [0] * 9)
    with pytest.raises(InvalidCounts):
        winning_number([True] + [0] * 9)   # bool must not pass as int


@pytest.mark.parametrize("bad", [(1, 1, 2), (1, 2), (1, 2, 3, 4), (1, 2, 10), (-1, 2, 3)])
def test_prediction_must_be_three_distinct_digits(bad):
    with pytest.raises(InvalidPrediction):
        validate_prediction(bad)


@pytest.mark.parametrize("bad", [10, -1, 1.0, True, "3"])
def test_vote_must_be_a_digit(bad):
    with pytest.raises(InvalidVote):
        validate_vote(bad)
