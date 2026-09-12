"""Round state machine."""

import itertools

import pytest

from domain.lifecycle import (
    ACCEPTING_ENTRIES,
    PROGRESSION,
    TRANSITIONS,
    IllegalTransition,
    RoundStatus,
    accepts_entries,
    inputs_frozen,
    is_legal,
    metrics_visible,
    next_status,
    require_legal,
)


def test_happy_path_is_a_chain():
    for frm, to in zip(PROGRESSION, PROGRESSION[1:], strict=False):
        assert is_legal(frm, to)
        assert next_status(frm) is to
    assert next_status(RoundStatus.REVEALED) is None


def test_every_pre_reveal_state_can_be_voided():
    for s in PROGRESSION:
        assert is_legal(s, RoundStatus.VOIDED) is (s is not RoundStatus.REVEALED)


def test_revealed_and_voided_are_terminal():
    for terminal in (RoundStatus.REVEALED, RoundStatus.VOIDED):
        assert not [t for (f, t) in TRANSITIONS if f is terminal]


def test_no_skipping_and_no_going_back():
    assert not is_legal(RoundStatus.OPEN, RoundStatus.SEALED)
    assert not is_legal(RoundStatus.OPEN, RoundStatus.REVEALED)
    assert not is_legal(RoundStatus.SEALED, RoundStatus.OPEN)
    assert not is_legal(RoundStatus.REVEALED, RoundStatus.OPEN)


def test_self_transition_is_a_legal_no_op():
    for s in RoundStatus:
        assert is_legal(s, s)


def test_require_legal_raises_with_both_ends_named():
    with pytest.raises(IllegalTransition) as exc:
        require_legal(RoundStatus.OPEN, RoundStatus.REVEALED)
    assert exc.value.frm is RoundStatus.OPEN
    assert exc.value.to is RoundStatus.REVEALED


def test_transition_table_has_no_unreachable_states():
    reachable = {RoundStatus.SCHEDULED}
    changed = True
    while changed:
        changed = False
        for frm, to in TRANSITIONS:
            if frm in reachable and to not in reachable:
                reachable.add(to)
                changed = True
    assert reachable == set(RoundStatus)


def test_exactly_the_intended_edges_exist():
    """Guards against an edge being added by accident."""
    assert len(TRANSITIONS) == len(PROGRESSION) - 1 + len(PROGRESSION) - 1


@pytest.mark.parametrize("status", list(RoundStatus))
def test_phase_predicates_are_total(status):
    assert isinstance(accepts_entries(status), bool)
    assert isinstance(metrics_visible(status), bool)
    assert isinstance(inputs_frozen(status), bool)


def test_entries_accepted_through_sealing_but_not_after():
    expected = {RoundStatus.OPEN, RoundStatus.BLACKOUT, RoundStatus.SEALING}
    assert expected == ACCEPTING_ENTRIES
    for s in (RoundStatus.SEALED, RoundStatus.RESOLVING, RoundStatus.REVEALED,
              RoundStatus.VOIDED, RoundStatus.SCHEDULED):
        assert not accepts_entries(s)


def test_blackout_hides_metrics_but_still_accepts_entries():
    """Ruleset V1.1 §6 — the dark hour is playable, just blind."""
    assert accepts_entries(RoundStatus.BLACKOUT)
    assert not metrics_visible(RoundStatus.BLACKOUT)
    assert metrics_visible(RoundStatus.OPEN)


def test_frozen_and_accepting_are_mutually_exclusive():
    for s in itertools.chain(RoundStatus):
        assert not (accepts_entries(s) and inputs_frozen(s))
