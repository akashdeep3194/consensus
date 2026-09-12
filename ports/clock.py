"""Time as a dependency.

Round boundaries are decided by authoritative timestamps, never by whatever
clock a process happens to have (§6.4). Injecting the clock is what makes the
lifecycle testable without sleeping.
"""

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, always timezone-aware UTC."""
        ...


class SystemClock:
    """Production clock."""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Test clock. Advances only when told to."""

    __slots__ = ("_now",)

    def __init__(self, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._now = now.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta) -> None:
        self._now += delta

    def set(self, now: datetime) -> None:
        self._now = now.astimezone(UTC)
