import pytest
import os

from base81 import list_codecs


@pytest.fixture(params=list_codecs())
def codec(request):
    """Parametrized fixture yielding (alphabet_type, block_size) for all registered codecs."""
    return request.param


@pytest.fixture
def sample_bytes():
    """Return a 256-byte sample of all byte values 0x00..0xFF."""
    return bytes(range(256))


@pytest.fixture
def random_bytes():
    """Return a random 1024-byte payload (different each test)."""
    return os.urandom(1024)


@pytest.fixture
def empty_bytes():
    return b""


@pytest.fixture
def large_bytes():
    """Return 1MB of random data for streaming tests."""
    return os.urandom(1024 * 1024)


@pytest.fixture(params=[(b"", ""), (b"a", "a"), (b"Hello", "Hello"), (os.urandom(100), None)])
def roundtrip_pair(request):
    """Parametrized (bytes, expected_encoded_str) for simple cases.
    If expected_encoded_str is None, we compute via encode and compare roundtrip."""
    data, expected = request.param
    return data, expected