import pytest
from base81._math import int_to_radix, radix_to_int, bytes_to_int, int_to_bytes
from base81._exceptions import CorruptStreamError, ValidationError
from base81._codecs import LOOKUPS


@pytest.mark.parametrize("alphabet_type", ["standard", "url"])
def test_radix_conversion_roundtrip(alphabet_type):
    cfg = LOOKUPS[alphabet_type]
    radix = cfg["base"]
    # Test all values from 0 to radix^3 - 1 (small range)
    for val in range(min(1000, radix**3)):
        s = int_to_radix(val, 3, cfg)
        assert len(s) == 3
        assert radix_to_int(s, cfg, 3) == val


def test_int_to_radix_overflow():
    cfg = LOOKUPS["standard"]
    with pytest.raises(CorruptStreamError):
        int_to_radix(81**9, 9, cfg)  # 81^9 is out of range for 9-digit base81


def test_radix_to_int_invalid_char():
    cfg = LOOKUPS["standard"]
    with pytest.raises(ValidationError, match="character '?' not in alphabet"):
        radix_to_int("?123", cfg, 4)


def test_radix_to_int_wrong_length():
    cfg = LOOKUPS["standard"]
    with pytest.raises(CorruptStreamError, match="length mismatch"):
        radix_to_int("ABC", cfg, 5)


def test_bytes_to_int_roundtrip():
    for i in range(256):
        b = bytes([i])
        assert int_to_bytes(bytes_to_int(b), 1) == b
    # 4-byte value
    val = 0x01020304
    assert bytes_to_int(int_to_bytes(val, 4)) == val


def test_int_to_bytes_overflow():
    with pytest.raises(ValueError, match="value too large"):
        int_to_bytes(256, 1)  # 256 doesn't fit in 1 byte