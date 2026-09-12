"""Project Consensus 3D — deterministic resolution engine.

Pure functions, zero I/O, zero third-party dependencies. Imported unchanged by
the API, the sealing worker, and the public audit CLI, so that an independent
party can reproduce any round from published data.

Ruleset: docs/00-ruleset.md
"""

from engine.canonical import EMPTY_ROOT, canonical_submission, leaf_hash, merkle_root
from engine.errors import (
    EngineError,
    InvalidCounts,
    InvalidPrediction,
    InvalidSubmissionSet,
    InvalidVote,
)
from engine.mandate import mandate_score, vote_share
from engine.rank import (
    full_ranking,
    validate_counts,
    validate_prediction,
    validate_vote,
    winning_number,
)
from engine.resolve import (
    AuditSlot,
    PlayerResult,
    RoundResult,
    Submission,
    resolve,
    tally,
    validate_submission_set,
)
from engine.tiers import Tier, tier_of
from engine.version import ALGORITHM_VERSION, RULESET_VERSION

__all__ = [
    "ALGORITHM_VERSION", "RULESET_VERSION", "EMPTY_ROOT",
    "EngineError", "InvalidCounts", "InvalidPrediction", "InvalidVote", "InvalidSubmissionSet",
    "Tier", "Submission", "PlayerResult", "AuditSlot", "RoundResult",
    "winning_number", "full_ranking", "tier_of", "mandate_score", "vote_share",
    "canonical_submission", "leaf_hash", "merkle_root",
    "resolve", "tally", "validate_submission_set",
    "validate_counts", "validate_prediction", "validate_vote",
]
