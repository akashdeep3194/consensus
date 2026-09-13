"""In-memory adapters.

Not only test doubles: they are the reference implementation of each port's
contract. The same conformance suite runs against these and against Postgres,
so a substitute that quietly behaves differently fails the build.
"""

from adapters.memory.repositories import (
    InMemoryDraftRepository,
    InMemoryRoundRepository,
    InMemorySubmissionRepository,
)
from adapters.memory.user_repository import InMemoryUserRepository
from ports.repositories import RoundClosed

__all__ = [
    "InMemoryDraftRepository",
    "InMemoryRoundRepository",
    "InMemorySubmissionRepository",
    "InMemoryUserRepository",
    "RoundClosed",
]

