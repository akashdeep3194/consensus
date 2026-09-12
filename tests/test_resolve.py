"""End-to-end round resolution."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from engine import Submission, Tier, resolve, tally


def sub(i, pred, vote, seq=None, eligible=False):
    return Submission(
        round_id="r1",
        submission_id=f"s{i}",
        user_id=f"u{i}",
        prediction=pred,
        vote=vote,
        commit_sequence=seq if seq is not None else i,
        mandate_eligible=eligible,
    )


def test_empty_round_resolves_to_012():
    r = resolve("r1", [])
    assert r.winning_number == (0, 1, 2)
    assert r.total_votes == 0
    assert r.commitment_root and r.players == []


def test_basic_round():
    subs = [
        sub(1, (9, 0, 3), 9), sub(2, (9, 0, 3), 9), sub(3, (0, 9, 3), 9),
        sub(4, (1, 2, 3), 0), sub(5, (1, 2, 3), 0), sub(6, (4, 5, 6), 3),
    ]
    r = resolve("r1", subs)
    assert tally(subs)[9] == 3
    assert r.winning_number == (9, 0, 3)
    assert r.tier_histogram[Tier.TRIFECTA] == 2
    assert r.tier_histogram[Tier.BOXED] == 1
    assert len(r.winners) == 2


def test_all_trifecta_holders_win_no_tie_break():
    subs = [sub(i, (0, 1, 2), 0) for i in range(1, 15)]
    r = resolve("r1", subs)
    assert len(r.winners) == 14
    assert all(w.tier is Tier.TRIFECTA for w in r.winners)


def test_mandate_board_excludes_ineligible_entries():
    subs = [
        sub(1, (5, 2, 7), 5, eligible=True),
        sub(2, (5, 2, 7), 5, eligible=False),
        sub(3, (1, 2, 3), 5, eligible=True),
    ]
    r = resolve("r1", subs)
    assert {p.submission_id for p in r.mandate_board} == {"s1", "s3"}
    assert r.mandate_board[0].mandate_rank == 1
    # an excluded entry still gets a tier and a score, just no rank
    ineligible = next(p for p in r.players if p.submission_id == "s2")
    assert ineligible.mandate_rank is None and ineligible.mandate_score > 0


def test_mandate_board_ties_share_a_rank():
    subs = [
        sub(1, (5, 2, 7), 5, eligible=True),
        sub(2, (5, 2, 7), 5, eligible=True),
        sub(3, (9, 8, 7), 5, eligible=True),
    ]
    r = resolve("r1", subs)
    ranks = {p.submission_id: p.mandate_rank for p in r.mandate_board}
    assert ranks["s1"] == ranks["s2"] == 1
    assert ranks["s3"] == 3          # competition ranking: 1, 1, 3


def test_mandate_board_is_topped_by_the_trifecta():
    """Votes 5/3/2 on digits 7/3/8 -> winner (7,3,8) with distinct counts."""
    votes = [7] * 5 + [3] * 3 + [8] * 2
    preds = [(7, 3, 8), (8, 3, 7), (7, 3, 0)] + [(1, 2, 4)] * 7
    subs = [
        sub(i, preds[i], votes[i], eligible=True) for i in range(len(votes))
    ]
    r = resolve("r1", subs)
    assert r.winning_number == (7, 3, 8)
    top = r.mandate_board[0]
    assert top.tier is Tier.TRIFECTA
    assert top.mandate_score == 23                   # 3*5 + 2*3 + 1*2
    scores = {p.prediction: p.mandate_score for p in r.mandate_board}
    assert scores[(7, 3, 0)] == 21                   # a TWO outscoring the BOXED entry
    assert scores[(8, 3, 7)] == 17


def test_audit_records_the_margin_and_flags_tie_breaks():
    subs = [sub(i, (1, 2, 3), 5) for i in range(1, 4)] + [
        sub(i, (1, 2, 3), 2) for i in range(4, 7)
    ]
    r = resolve("r1", subs)
    assert r.winning_number[0] == 2          # 2 and 5 tie at 3 -> lower digit
    assert r.audit[0].digit == 2 and r.audit[0].votes == 3
    assert r.audit[0].margin == 0 and r.audit[0].decided_by_tie_break is True
    assert r.audit[1].digit == 5 and r.audit[1].margin == 3


def test_commit_order_changes_the_root_but_not_the_outcome():
    a = [sub(1, (1, 2, 3), 1, seq=1), sub(2, (4, 5, 6), 4, seq=2)]
    b = [sub(1, (1, 2, 3), 1, seq=2), sub(2, (4, 5, 6), 4, seq=1)]
    ra, rb = resolve("r1", a), resolve("r1", b)
    assert ra.winning_number == rb.winning_number
    assert ra.commitment_root != rb.commitment_root


def test_submission_order_in_the_list_is_irrelevant():
    subs = [sub(1, (1, 2, 3), 1), sub(2, (4, 5, 6), 4), sub(3, (7, 8, 9), 7)]
    a = resolve("r1", subs)
    b = resolve("r1", list(reversed(subs)))
    assert a.winning_number == b.winning_number
    assert a.commitment_root == b.commitment_root
    assert a.tier_histogram == b.tier_histogram


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.lists(st.integers(0, 9), min_size=3, max_size=3, unique=True).map(tuple),
            st.integers(0, 9),
        ),
        min_size=0,
        max_size=60,
    )
)
def test_resolution_is_deterministic(entries):
    subs = [sub(i, p, v) for i, (p, v) in enumerate(entries)]
    a, b = resolve("r1", subs), resolve("r1", subs)
    assert a.winning_number == b.winning_number
    assert a.commitment_root == b.commitment_root
    assert a.tier_histogram == b.tier_histogram
    assert sum(a.tier_histogram.values()) == len(subs)


def test_prediction_with_repeated_digits_is_rejected_at_construction():
    from engine import InvalidPrediction

    with pytest.raises(InvalidPrediction):
        sub(1, (1, 1, 2), 0)


# ── structural invariants of the committed set ──────────────────────
# Regression tests. Each of these silently produced a wrong-but-plausible
# result before validate_submission_set() existed.


def test_duplicate_commit_sequence_is_rejected():
    """Ambiguous leaf order would make the commitment root irreproducible."""
    from engine import InvalidSubmissionSet

    subs = [sub(1, (1, 2, 3), 1, seq=7), sub(2, (4, 5, 6), 4, seq=7)]
    with pytest.raises(InvalidSubmissionSet, match="commit_sequence"):
        resolve("r1", subs)


def test_duplicate_submission_id_is_rejected():
    from engine import InvalidSubmissionSet

    subs = [
        Submission("r1", "dup", "u1", (1, 2, 3), 1, 1),
        Submission("r1", "dup", "u2", (4, 5, 6), 4, 2),
    ]
    with pytest.raises(InvalidSubmissionSet, match="submission_id"):
        resolve("r1", subs)


def test_one_entry_per_account_per_round_is_enforced():
    from engine import InvalidSubmissionSet

    subs = [
        Submission("r1", "s1", "same-user", (1, 2, 3), 1, 1),
        Submission("r1", "s2", "same-user", (4, 5, 6), 4, 2),
    ]
    with pytest.raises(InvalidSubmissionSet, match="one entry per account"):
        resolve("r1", subs)


def test_submission_from_another_round_is_rejected():
    """The root must commit to the round it is reported against."""
    from engine import InvalidSubmissionSet

    subs = [Submission("OTHER", "s1", "u1", (1, 2, 3), 1, 1)]
    with pytest.raises(InvalidSubmissionSet, match="belongs to round"):
        resolve("r1", subs)


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.lists(st.integers(0, 9), min_size=3, max_size=3, unique=True).map(tuple),
            st.integers(0, 9),
        ),
        min_size=1,
        max_size=40,
    ),
    st.randoms(use_true_random=False),
)
def test_root_never_depends_on_argument_order(entries, rng):
    """The strong form of the determinism guarantee, over shuffled inputs."""
    subs = [sub(i, p, v, seq=i) for i, (p, v) in enumerate(entries)]
    shuffled = list(subs)
    rng.shuffle(shuffled)
    a, b = resolve("r1", subs), resolve("r1", shuffled)
    assert a.commitment_root == b.commitment_root
    assert a.winning_number == b.winning_number
    assert [p.submission_id for p in a.players] == [p.submission_id for p in b.players]
    assert [p.mandate_rank for p in a.mandate_board] == [
        p.mandate_rank for p in b.mandate_board
    ]


def test_mandate_board_order_is_stable_under_score_ties():
    """Tied scores resolve by commit_sequence, never by argument order."""
    subs = [
        sub(1, (5, 2, 7), 5, seq=10, eligible=True),
        sub(2, (5, 2, 7), 5, seq=20, eligible=True),
        sub(3, (5, 2, 7), 5, seq=30, eligible=True),
    ]
    forward = [p.submission_id for p in resolve("r1", subs).mandate_board]
    backward = [p.submission_id for p in resolve("r1", list(reversed(subs))).mandate_board]
    assert forward == backward == ["s1", "s2", "s3"]
