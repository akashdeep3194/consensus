"""Frozen behaviour gate.

If this fails, resolution behaviour changed. That is only acceptable alongside a
deliberate ALGORITHM_VERSION bump and a regenerated vector file.
"""

import json
import pathlib

import pytest

from engine.version import ALGORITHM_VERSION, RULESET_VERSION
from tests.make_golden import build

GOLDEN = json.loads((pathlib.Path(__file__).parent / "golden_vectors.json").read_text())


def test_versions_match_the_frozen_file():
    assert GOLDEN["algorithm_version"] == ALGORITHM_VERSION
    assert GOLDEN["ruleset_version"] == RULESET_VERSION


@pytest.mark.parametrize("case", GOLDEN["cases"], ids=lambda c: c["name"])
def test_case_reproduces_exactly(case):
    entries = [(e["vote"], tuple(e["prediction"])) for e in case["entries"]]
    actual = build(case["name"], entries)
    assert actual == case
