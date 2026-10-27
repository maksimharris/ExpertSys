import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from programs import common  # noqa: E402


@pytest.fixture(scope="session")
def data():
    return common.load_data()


@pytest.fixture(scope="session")
def baseline(data):
    return common.baseline_data(data)
