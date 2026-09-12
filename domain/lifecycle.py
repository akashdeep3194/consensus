"""Round state machine — the canonical definition.

`db/migrations/0001_init.sql` mirrors this table into `round_transitions`, and
`tests/test_lifecycle.py` asserts the two agree. Python is the source of truth;
the database is the enforcement point.

Transitions are **data, not branching logic**: adding a phase means adding an
edge, never editing a function. Open for extension, closed for modification.
"""

from enum import StrEnum
from types import MappingProxyType


class RoundStatus(StrEnum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    BLACKOUT = "blackout"
    SEALING = "sealing"
    SEALED = "sealed"
    RESOLVING = "resolving"
    REVEALED = "revealed"
    VOIDED = "voided"


#: The happy path, in order.
PROGRESSION: tuple[RoundStatus, ...] = (
    RoundStatus.SCHEDULED,
    RoundStatus.OPEN,
    RoundStatus.BLACKOUT,
    RoundStatus.SEALING,
    RoundStatus.SEALED,
    RoundStatus.RESOLVING,
    RoundStatus.REVEALED,
)

#: A round may be abandoned from any state before it is revealed.
_ABANDONABLE = tuple(s for s in PROGRESSION if s is not RoundStatus.REVEALED)

TRANSITIONS: frozenset[tuple[RoundStatus, RoundStatus]] = frozenset(
    list(zip(PROGRESSION, PROGRESSION[1:], strict=False))
    + [(s, RoundStatus.VOIDED) for s in _ABANDONABLE]
)

#: Phases during which the round accepts draft edits and lock-ins.
ACCEPTING_ENTRIES: frozenset[RoundStatus] = frozenset(
    {RoundStatus.OPEN, RoundStatus.BLACKOUT, RoundStatus.SEALING}
)

#: Phases during which live aggregate metrics may be served.
METRICS_VISIBLE: frozenset[RoundStatus] = frozenset({RoundStatus.OPEN})

#: Phases in which the committed input set is final.
INPUTS_FROZEN: frozenset[RoundStatus] = frozenset(
    {RoundStatus.SEALED, RoundStatus.RESOLVING, RoundStatus.REVEALED}
)

_NEXT: MappingProxyType[RoundStatus, RoundStatus] = MappingProxyType(
    dict(zip(PROGRESSION, PROGRESSION[1:], strict=False))
)


class IllegalTransition(ValueError):
    """Raised when a transition is not an edge of the state machine."""

    def __init__(self, frm: RoundStatus, to: RoundStatus) -> None:
        super().__init__(f"illegal round transition {frm} -> {to}")
        self.frm, self.to = frm, to


def is_legal(frm: RoundStatus, to: RoundStatus) -> bool:
    """A no-op transition is legal; anything not an edge is not."""
    return frm is to or (frm, to) in TRANSITIONS


def require_legal(frm: RoundStatus, to: RoundStatus) -> None:
    if not is_legal(frm, to):
        raise IllegalTransition(frm, to)


def next_status(frm: RoundStatus) -> RoundStatus | None:
    """The next status on the happy path, or None at a terminal state."""
    return _NEXT.get(frm)


def accepts_entries(status: RoundStatus) -> bool:
    return status in ACCEPTING_ENTRIES


def metrics_visible(status: RoundStatus) -> bool:
    """Ruleset V1.1 §6: live standings are hidden from blackout onward."""
    return status in METRICS_VISIBLE


def inputs_frozen(status: RoundStatus) -> bool:
    return status in INPUTS_FROZEN
