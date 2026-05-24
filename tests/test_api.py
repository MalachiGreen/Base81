"""Tests for high-level encode/decode API."""

import pytest
from base81 import encode, decode
from base81._exceptions import ValidationError, CorruptStreamError, BoundaryError


class TestEncodeBasic:
    def test_empty_bytes(self):
        assert encode(b"") == ""

    @pytest.mark.parametrize("block_size,alphabet", [
        (3, "standard"), (7, "standard"), (5, "url")
    ])
    def test_single_byte(self, block_size, alphabet):
        for i in range(256):
            data = bytes([i])
            encoded = encode(data, block_size=block_size, alphabet_type=alphabet)
            decoded = decode(encoded, block_size=block_size, alphabet_type=alphabet)
            assert decoded == data

    def test_type_check(self):
        with pytest.raises(TypeError, match="bytes required"):
            encode("not bytes")  # type: ignore

    def test_unknown_codec(self):
        with pytest.raises(ValidationError, match="unknown codec"):
            encode(b"test", block_size=99, alphabet_type="standard")


class TestEncodeLineWrapping:
    def test_line_width_int(self):
        data = b"x" * 100
        encoded = encode(data, line_width=20)
        lines = encoded.split('\n')
        assert all(len(line) <= 20 for line in lines)
        assert len(lines) > 1

    def test_line_width_none(self):
        data = b"x" * 100
        encoded = encode(data, line_width=None)
        assert '\n' not in encoded

    def test_invalid_line_width(self):
        with pytest.raises(ValidationError):
            encode(b"test", line_width=0)
        with pytest.raises(ValidationError):
            encode(b"test", line_width=True)  # type: ignore


class TestDecodeBasic:
    def test_empty_string(self):
        assert decode("") == b""

    def test_type_check(self):
        with pytest.raises(TypeError, match="str required"):
            decode(b"not string")  # type: ignore

    def test_whitespace_strict(self):
        encoded = encode(b"test")
        with pytest.raises(ValidationError, match="whitespace"):
            decode(f" {encoded}")

    def test_whitespace_ignored(self):
        encoded = encode(b"test")
        result = decode(f" \t{encoded}\n", ignore_whitespace=True)
        assert result == b"test"

    def test_max_input_length(self):
        encoded = encode(b"x" * 1000)
        with pytest.raises(BoundaryError, match="input too long"):
            decode(encoded, max_input_length=100)


class TestRoundtrip:
    @pytest.mark.parametrize("block_size,alphabet", [
        (3, "standard"), (7, "standard"), (5, "url")
    ])
    @pytest.mark.parametrize("size", [0, 1, 2, 3, 7, 8, 100, 1000])
    def test_roundtrip_various_sizes(self, block_size, alphabet, size):
        import os
        data = os.urandom(size)
        encoded = encode(data, block_size=block_size, alphabet_type=alphabet)
        decoded = decode(encoded, block_size=block_size, alphabet_type=alphabet)
        assert decoded == data

    def test_canonical_validation_enabled_by_default(self):
        # Create non-canonical encoding manually
        data = b"\x01"
        encoded = encode(data, block_size=7)  # Should be canonical
        # Tamper with tail to create non-canonical
        corrupted = encoded[:-1] + "A"  # Change last char
        with pytest.raises(ValidationError, match="non-canonical"):
            decode(corrupted, block_size=7)

    def test_canonical_validation_disabled(self):
        data = b"\x01"
        encoded = encode(data, block_size=7)
        corrupted = encoded[:-1] + "A"
        # Should still work but produce different bytes
        result = decode(corrupted, block_size=7, validate_canonical=False)
        assert result != data  # Non-canonical decodes to different data


class TestEdgeCases:
    def test_all_bytes_values(self):
        for i in range(256):
            data = bytes([i])
            for bs, alpha in [(3, "standard"), (7, "standard"), (5, "url")]:
                encoded = encode(data, block_size=bs, alphabet_type=alpha)
                decoded = decode(encoded, block_size=bs, alphabet_type=alpha)
                assert decoded == data

    def test_repeated_pattern(self):
        pattern = b"\x00\xff\x55\xaa" * 100
        for bs, alpha in [(3, "standard"), (7, "standard"), (5, "url")]:
            encoded = encode(pattern, block_size=bs, alphabet_type=alpha)
            decoded = decode(encoded, block_size=bs, alphabet_type=alpha)
            assert decoded == pattern

    def test_maximum_block_size_data(self):
        data = b"\xff" * 10000
        encoded = encode(data, block_size=7, alphabet_type="standard")
        decoded = decode(encoded, block_size=7, alphabet_type="standard")
        assert decoded == data