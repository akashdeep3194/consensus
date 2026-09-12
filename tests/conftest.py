import itertools

import pytest

ALL_PREDICTIONS = tuple(itertools.permutations(range(10), 3))  # the 720 valid slates


def pytest_configure(config):
    config.addinivalue_line("markers", "exhaustive: full 720x720 sweep; slow")


@pytest.fixture(scope="session")
def all_predictions():
    return ALL_PREDICTIONS
