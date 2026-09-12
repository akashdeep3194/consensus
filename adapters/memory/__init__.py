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

__all__ = [
    "InMemoryDraftRepository",
    "InMemoryRoundRepository",
    "InMemorySubmissionRepository",
]
