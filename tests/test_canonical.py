"""Canonical encoding and Merkle commitment."""

import hashlib

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine import EMPTY_ROOT, canonical_submission, leaf_hash, merkle_root
from engine.version import ALGORITHM_VERSION


def test_canonical_string_is_exactly_specified():
    s = canonical_submission("r1", "s1", (5, 2, 7), 3, 42)
    assert s == f"{ALGORITHM_VERSION}|r1|s1|527|3|42"


def test_canonical_binds_the_algorithm_version():
    assert canonical_submission("r1", "s1", (5, 2, 7), 3, 42).startswith(ALGORITHM_VERSION)


def test_leading_zero_prediction_is_unambiguous():
    assert canonical_submission("r", "s", (0, 1, 2), 0, 0).endswith("|012|0|0")


@pytest.mark.parametrize("bad_id", ["a|b", "", "a b", "x" * 65, "a/b", 7])
def test_ids_cannot_contain_the_separator(bad_id):
    with pytest.raises(ValueError):
        canonical_submission(bad_id, "s1", (1, 2, 3), 0, 0)


def test_commit_sequence_must_be_a_non_negative_int():
    with pytest.raises(ValueError):
        canonical_submission("r", "s", (1, 2, 3), 0, -1)
    with pytest.raises(ValueError):
        canonical_submission("r", "s", (1, 2, 3), 0, True)


# ── merkle ──────────────────────────────────────────────────────────
def test_empty_round_has_a_defined_root():
    assert merkle_root([]) == EMPTY_ROOT
    assert len(EMPTY_ROOT) == 64


def test_single_leaf_root_is_that_leaf():
    leaf = leaf_hash("x")
    assert merkle_root([leaf]) == leaf.hex()


def test_leaf_and_node_hashes_are_domain_separated():
    """A leaf must never be constructible as an internal node."""
    a, b = leaf_hash("a"), leaf_hash("b")
    node = hashlib.sha256(b"\x01" + a + b).digest()
    assert node != hashlib.sha256(b"\x00" + a + b).digest()
    assert merkle_root([a, b]) == node.hex()


def test_odd_node_is_promoted_not_duplicated():
    """Duplicating the last node (Bitcoin's approach) admits CVE-2012-2459."""
    a, b, c = (leaf_hash(x) for x in "abc")
    ab = hashlib.sha256(b"\x01" + a + b).digest()
    expected = hashlib.sha256(b"\x01" + ab + c).digest().hex()
    assert merkle_root([a, b, c]) == expected
    # the duplication attack: [a,b,c,c] must NOT collide with [a,b,c]
    assert merkle_root([a, b, c, c]) != merkle_root([a, b, c])


def test_order_matters():
    a, b = leaf_hash("a"), leaf_hash("b")
    assert merkle_root([a, b]) != merkle_root([b, a])


@given(st.lists(st.text(min_size=1, max_size=12), min_size=0, max_size=40))
def test_root_is_deterministic_and_hex(items):
    leaves = [leaf_hash(i) for i in items]
    r = merkle_root(leaves)
    assert r == merkle_root(list(leaves))
    assert len(r) == 64 and int(r, 16) >= 0


@given(st.lists(st.text(min_size=1, max_size=8), min_size=1, max_size=25, unique=True))
def test_changing_any_leaf_changes_the_root(items):
    leaves = [leaf_hash(i) for i in items]
    base = merkle_root(leaves)
    mutated = [leaf_hash("MUTATED")] + leaves[1:]
    assert merkle_root(mutated) != base
