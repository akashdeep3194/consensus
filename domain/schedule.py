"""Round scheduling — pure timing arithmetic.

Cadence is **daily and overlapping** (Q3): a round runs 24h of entry plus 6h of
resolution, so round N is still resolving six hours into round N+1. Two rounds
are live at once by design.

Offsets are injected rather than hard-coded, so changing the cadence is a
configuration decision rather than a code change.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from domain.lifecycle import RoundStatus


@dataclass(frozen=True, slots=True)
class RoundTiming:
    """Phase offsets from a round's opening instant.
    
    Game runs 23.5 hours (00:00 UTC to 23:30 UTC), then results revealed at 00:00 UTC next day.
    """

    mandate_deadline: timedelta = timedelta(hours=12)   # Board B eligibility, S3
    blackout: timedelta = timedelta(hours=23)
    seal: timedelta = timedelta(hours=23, minutes=30)   # Seal at 23:30 UTC
    reveal: timedelta = timedelta(days=1)                # Reveal at 00:00 UTC next day
    cadence: timedelta = timedelta(days=1)              # Next round opens at 00:00 UTC

    def __post_init__(self) -> None:
        ordered = (self.mandate_deadline, self.blackout, self.seal, self.reveal)
        if not all(a < b for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError(f"phase offsets must strictly increase, got {ordered}")
        if self.mandate_deadline <= timedelta(0):
            raise ValueError("mandate deadline must fall after the round opens")


DEFAULT_TIMING = RoundTiming()


@dataclass(frozen=True, slots=True)
class RoundSchedule:
    """The canonical boundaries of one round. All instants are UTC."""

    cycle_number: int
    opens_at: datetime
    mandate_deadline: datetime
    blackout_at: datetime
    seals_at: datetime
    reveals_at: datetime

    def status_at(self, now: datetime) -> RoundStatus:
        """The phase this round *should* be in at `now`.

        Advisory only. The database is authoritative for the phase a round is
        actually in (§6.1); this tells a scheduler what is due, never what is
        true.
        """
        if now < self.opens_at:
            return RoundStatus.SCHEDULED
        if now < self.blackout_at:
            return RoundStatus.OPEN
        if now < self.seals_at:
            return RoundStatus.BLACKOUT
        if now < self.reveals_at:
            return RoundStatus.SEALING
        return RoundStatus.REVEALED

    def mandate_eligible(self, committed_at: datetime) -> bool:
        """Ruleset V1.1 §3.2 — Board B counts only entries locked before T+12h."""
        return committed_at < self.mandate_deadline


def schedule_for(
    cycle_number: int,
    anchor: datetime,
    timing: RoundTiming = DEFAULT_TIMING,
) -> RoundSchedule:
    """Boundaries for `cycle_number`, counted from `anchor` (cycle 0's opening)."""
    if cycle_number < 0:
        raise ValueError(f"cycle_number must be non-negative, got {cycle_number}")
    if anchor.tzinfo is None:
        raise ValueError("anchor must be timezone-aware; round boundaries are UTC")
    opens = (anchor + cycle_number * timing.cadence).astimezone(UTC)
    return RoundSchedule(
        cycle_number=cycle_number,
        opens_at=opens,
        mandate_deadline=opens + timing.mandate_deadline,
        blackout_at=opens + timing.blackout,
        seals_at=opens + timing.seal,
        reveals_at=opens + timing.reveal,
    )


def live_cycles(now: datetime, anchor: datetime, timing: RoundTiming = DEFAULT_TIMING) -> list[int]:
    """Cycle numbers that have opened but not yet revealed at `now`.

    Under the default timing this returns two rounds for most of the day — the
    overlap is the point, not an edge case.
    """
    if now < anchor:
        return []
    elapsed = now - anchor
    newest = int(elapsed // timing.cadence)
    span = int(timing.reveal // timing.cadence) + 1
    return [
        c
        for c in range(max(0, newest - span), newest + 1)
        if schedule_for(c, anchor, timing).opens_at <= now
        and now < schedule_for(c, anchor, timing).reveals_at
    ]
