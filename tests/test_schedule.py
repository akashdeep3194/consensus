"""Round scheduling.

Q3's original design overlapped rounds by 6 hours (24h to seal, 6 more to
resolve, so N+1 opens while N is still resolving). The 23.5h/24h timing below
replaced that with a 30-minute resolution window and a back-to-back handoff
instead — round N reveals at the exact instant round N+1 opens, with no gap
and no overlap. The tests below assert *that* property now, not the old one.
"""

from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.lifecycle import RoundStatus
from domain.schedule import RoundTiming, live_cycles, schedule_for

ANCHOR = datetime(2026, 9, 12, tzinfo=UTC)


def test_default_offsets_match_the_ruleset():
    s = schedule_for(0, ANCHOR)
    assert s.opens_at == ANCHOR
    assert s.mandate_deadline == ANCHOR + timedelta(hours=12)
    assert s.blackout_at == ANCHOR + timedelta(hours=23)
    assert s.seals_at == ANCHOR + timedelta(hours=23, minutes=30)
    assert s.reveals_at == ANCHOR + timedelta(hours=24)


def test_cycles_open_one_day_apart():
    assert schedule_for(5, ANCHOR).opens_at - schedule_for(4, ANCHOR).opens_at == timedelta(days=1)


def test_rounds_hand_off_with_no_gap_or_overlap():
    """Reveal is set to the cadence exactly: round N+1 opens at the same
    instant round N reveals, neither before it nor after a dead gap."""
    a, b = schedule_for(0, ANCHOR), schedule_for(1, ANCHOR)
    assert b.opens_at == a.reveals_at


def test_only_the_incoming_round_is_live_at_the_handoff_instant():
    handoff = schedule_for(0, ANCHOR).reveals_at   # == schedule_for(1, ANCHOR).opens_at
    assert live_cycles(handoff, ANCHOR) == [1]
    assert live_cycles(handoff - timedelta(seconds=1), ANCHOR) == [0]


def test_one_round_live_mid_cycle():
    assert live_cycles(ANCHOR + timedelta(hours=12), ANCHOR) == [0]


def test_nothing_live_before_the_anchor():
    assert live_cycles(ANCHOR - timedelta(hours=1), ANCHOR) == []


@pytest.mark.parametrize(
    "offset,expected",
    [
        (timedelta(hours=-1), RoundStatus.SCHEDULED),
        (timedelta(0), RoundStatus.OPEN),
        (timedelta(hours=22, minutes=59), RoundStatus.OPEN),
        (timedelta(hours=23), RoundStatus.BLACKOUT),
        (timedelta(hours=23, minutes=29), RoundStatus.BLACKOUT),
        (timedelta(hours=23, minutes=30), RoundStatus.SEALING),
        (timedelta(hours=23, minutes=59), RoundStatus.SEALING),
        (timedelta(hours=24), RoundStatus.REVEALED),
    ],
)
def test_status_at_boundaries(offset, expected):
    assert schedule_for(0, ANCHOR).status_at(ANCHOR + offset) is expected


def test_mandate_eligibility_is_strictly_before_the_deadline():
    s = schedule_for(0, ANCHOR)
    assert s.mandate_eligible(s.mandate_deadline - timedelta(seconds=1))
    assert not s.mandate_eligible(s.mandate_deadline)
    assert not s.mandate_eligible(s.mandate_deadline + timedelta(seconds=1))


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        schedule_for(0, datetime(2026, 9, 12))


def test_negative_cycle_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        schedule_for(-1, ANCHOR)


def test_timing_offsets_must_increase():
    with pytest.raises(ValueError, match="strictly increase"):
        RoundTiming(mandate_deadline=timedelta(hours=25), blackout=timedelta(hours=23))


def test_custom_timing_is_honoured():
    """Cadence is configuration, not a code change."""
    fast = RoundTiming(
        mandate_deadline=timedelta(minutes=30),
        blackout=timedelta(minutes=50),
        seal=timedelta(hours=1),
        reveal=timedelta(hours=2),
        cadence=timedelta(hours=1),
    )
    s = schedule_for(3, ANCHOR, fast)
    assert s.opens_at == ANCHOR + timedelta(hours=3)
    assert s.reveals_at == ANCHOR + timedelta(hours=5)


@given(st.integers(min_value=0, max_value=10_000))
def test_phases_are_always_strictly_ordered(cycle):
    s = schedule_for(cycle, ANCHOR)
    assert s.opens_at < s.mandate_deadline < s.blackout_at < s.seals_at < s.reveals_at


@given(st.integers(min_value=0, max_value=1000), st.integers(min_value=0, max_value=23))
def test_status_at_agrees_with_liveness(cycle, hours):
    """Bounded to hour 23: reveal lands at hour 24 exactly, with no overlap
    for a next cycle to still be counted through — see the handoff tests."""
    s = schedule_for(cycle, ANCHOR)
    now = s.opens_at + timedelta(hours=hours)
    assert s.status_at(now) is not RoundStatus.REVEALED
    assert cycle in live_cycles(now, ANCHOR)
