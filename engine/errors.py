"""Engine-level validation errors. The engine never raises anything else."""


class EngineError(ValueError):
    """Base class for all engine validation failures."""


class InvalidCounts(EngineError):
    """The vote-count vector is not ten non-negative integers."""


class InvalidPrediction(EngineError):
    """A prediction is not three distinct digits in 0-9."""


class InvalidVote(EngineError):
    """A vote is not a single digit in 0-9."""


class InvalidSubmissionSet(EngineError):
    """The committed submission set violates a structural invariant.

    Raised rather than silently resolving: a malformed set would produce a
    wrong-but-plausible result, which is the worst possible failure here.
    """
