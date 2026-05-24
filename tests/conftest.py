"""Pytest configuration and fixtures."""

import pytest
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def random_bytes():
    """Generate random bytes of specified size."""
    import os
    def _random_bytes(size):
        return os.urandom(size)
    return _random_bytes


@pytest.fixture
def all_codecs():
    """Return list of all (alphabet, block_size) tuples."""
    return [("standard", 3), ("standard", 7), ("url", 5)]


def pytest_configure(config):
    """Mark slow tests."""
    config.addinivalue_line("markers", "slow: marks tests as slow running")