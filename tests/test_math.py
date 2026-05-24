"""Tests for radix conversion primitives."""

import pytest
from base81._math import (
    int_to_radix, radix_to_int, bytes_to_int, int_to_bytes, POW
)
from base81._codecs import LOOKUPS
from base81._exceptions import CorruptStreamError, ValidationError


class TestPowTable:
    def test_precomputed_values(self):
        assert POW[81][0] == 1
        assert POW[81][1] == 81
        assert POW[81][2] == 6561
        assert POW[62][0] == 1
        assert POW[62][1] == 62
        assert POW[256][0] == 1
        assert POW[256][1] == 256
        assert POW[256][2] == 65536

    def test_pow_monotonic(self):
        for base in [62, 81, 256]:
            for i in range(1, 16):
                assert POW[base][i] > POW[base][i-1]

    def test_max_exponent(self):
        assert len(POW[81]) == 17  # 0..16
        assert len(POW[62]) == 17
        assert len(POW[256]) == 17


class TestIntToRadix:
    @pytest.fixture
    def alpha_cfg(self):
        return LOOKUPS["standard"]

    def test_zero(self, alpha_cfg):
        result = int_to_radix(0, 4, alpha_cfg)
        assert result == "0000"
        assert len(result) == 4

    def test_small_value(self, alpha_cfg):
        result = int_to_radix(42, 2, alpha_cfg)
        assert len(result) == 2
        # 42 in base81 is '0'*42? Actually digit 42 = 'q'? Let's verify roundtrip
        back = radix_to_int(result, alpha_cfg, 2)
        assert back == 42

    def test_max_value(self, alpha_cfg):
        radix = alpha_cfg["base"]
        max_val = POW[radix][4] - 1
        result = int_to_radix(max_val, 4, alpha_cfg)
        back = radix_to_int(result, alpha_cfg, 4)
        assert back == max_val

    def test_overflow_raises(self, alpha_cfg):
        radix = alpha_cfg["base"]
        overflow = POW[radix][3]
        with pytest.raises(CorruptStreamError, match="overflow"):
            int_to_radix(overflow, 3, alpha_cfg)

    def test_negative_raises(self, alpha_cfg):
        with pytest.raises(Exception):  # CodecError
            int_to_radix(-1, 4, alpha_cfg)


class TestRadixToInt:
    @pytest.fixture
    def alpha_cfg(self):
        return LOOKUPS["standard"]

    def test_valid_string(self, alpha_cfg):
        # "0000" = 0
        assert radix_to_int("0000", alpha_cfg, 4) == 0

    def test_invalid_char_raises(self, alpha_cfg):
        with pytest.raises(ValidationError, match="not in alphabet"):
            radix_to_int("ABC$", alpha_cfg, 4)

    def test_length_mismatch_raises(self, alpha_cfg):
        with pytest.raises(CorruptStreamError, match="length mismatch"):
            radix_to_int("abc", alpha_cfg, 4)

    def test_max_value(self, alpha_cfg):
        radix = alpha_cfg["base"]
        max_str = alpha_cfg["to_char"][-1] * 4  # Highest digit repeated
        # This might overflow - need actual max value
        # Simpler: encode then decode
        max_val = POW[radix][4] - 1
        encoded = int_to_radix(max_val, 4, alpha_cfg)
        decoded = radix_to_int(encoded, alpha_cfg, 4)
        assert decoded == max_val


class TestBytesIntRoundtrip:
    def test_single_byte(self):
        for i in range(256):
            b = bytes([i])
            val = bytes_to_int(b)
            assert val == i
            assert int_to_bytes(val, 1) == b

    def test_multi_byte(self):
        test_cases = [
            b"\x00\x00",
            b"\x00\x01",
            b"\xff\xff",
            b"\x12\x34\x56",
            b"\x00" * 8,
            b"\xff" * 8,
        ]
        for b in test_cases:
            val = bytes_to_int(b)
            recovered = int_to_bytes(val, len(b))
            assert recovered == b

    def test_int_to_bytes_overflow(self):
        with pytest.raises(ValueError, match="too large"):
            int_to_bytes(256, 1)  # 256 needs 2 bytes

    def test_bytes_to_int_preserves_order(self):
        assert bytes_to_int(b"\x01\x00") > bytes_to_int(b"\x00\xff")