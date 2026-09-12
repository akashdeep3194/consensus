"""Canonical encoding and Merkle commitment. Ruleset V1.1 / v2.1 §8.3.

Canonicalisation must be reproducible by an independent implementation, so every
choice here is explicit: field order, separator, padding, hash, leaf/internal
domain separation, and odd-node handling.

    canonical = "<algorithm_version>|<round_id>|<submission_id>|<PPP>|<V>|<seq>"

Fields are joined with "|". `round_id` and `submission_id` are restricted to
[A-Za-z0-9_-] so the separator can never appear inside a field. The prediction is
three digits with no padding ambiguity; the vote is one digit; commit_sequence is
decimal with no leading zeros.

Leaves are hashed in commit_sequence order.
"""

import hashlib
import re
from collections.abc import Iterable, Sequence

from engine.rank import validate_prediction, validate_vote
from engine.version import ALGORITHM_VERSION

SEPARATOR = "|"
#: UUIDs (with hyphens) satisfy this; the separator can never appear inside a field.
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Domain-separation prefixes keep a leaf hash from ever colliding with an
# internal-node hash (second-preimage resistance).
_LEAF_PREFIX = b"\x00"
_NODE_PREFIX = b"\x01"

#: Root of a round that sealed with no committed submissions.
EMPTY_ROOT = hashlib.sha256(b"\x02consensus-empty-round").hexdigest()


def _check_id(name: str, value: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(f"{name} must match {_ID_RE.pattern}, got {value!r}")
    return value


def canonical_submission(
    round_id: str,
    submission_id: str,
    prediction: Sequence[int],
    vote: int,
    commit_sequence: int,
) -> str:
    """The exact string an independent auditor must reproduce."""
    _check_id("round_id", round_id)
    _check_id("submission_id", submission_id)
    p = validate_prediction(prediction)
    v = validate_vote(vote)
    if not isinstance(commit_sequence, int) or isinstance(commit_sequence, bool):
        raise ValueError(f"commit_sequence must be an int, got {commit_sequence!r}")
    if commit_sequence < 0:
        raise ValueError(f"commit_sequence must be non-negative, got {commit_sequence}")
    return SEPARATOR.join(
        [
            ALGORITHM_VERSION,
            round_id,
            submission_id,
            "".join(str(d) for d in p),
            str(v),
            str(commit_sequence),
        ]
    )


def leaf_hash(canonical: str) -> bytes:
    return hashlib.sha256(_LEAF_PREFIX + canonical.encode("utf-8")).digest()


def merkle_root(leaves: Iterable[bytes]) -> str:
    """Merkle root as lowercase hex.

    An odd node at any level is **promoted unchanged** to the next level rather
    than duplicated. Duplication (the Bitcoin approach) admits distinct leaf sets
    that produce identical roots — CVE-2012-2459.
    """
    level = list(leaves)
    if not level:
        return EMPTY_ROOT
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level) - 1, 2):
            nxt.append(hashlib.sha256(_NODE_PREFIX + level[i] + level[i + 1]).digest())
        if len(level) % 2:
            nxt.append(level[-1])  # promote, never duplicate
        level = nxt
    return level[0].hex()
