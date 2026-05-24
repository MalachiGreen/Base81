"""Tests for header parsing and generation."""

import pytest
from base81._header import make_header, parse_header
from base81._exceptions import ValidationError


class TestMakeHeader:
    def test_standard_header(self):
        header = make_header(7, "standard")
        assert header == "^b81:7:standard^"

    def test_url_header(self):
        header = make_header(5, "url")
        assert header == "^b81:5:url^"

    def test_header_format(self):
        header = make_header(3, "standard")
        assert header.startswith("^b81:")
        assert header.endswith("^")


class TestParseHeader:
    def test_parse_valid_header(self):
        bs, alpha, payload = parse_header("^b81:7:standard^HelloWorld")
        assert bs == 7
        assert alpha == "standard"
        assert payload == "HelloWorld"

    def test_parse_with_leading_whitespace(self):
        bs, alpha, payload = parse_header("  \t\n^b81:3:standard^data")
        assert bs == 3
        assert alpha == "standard"
        assert payload == "data"

    def test_parse_payload_only(self):
        with pytest.raises(ValidationError, match="missing header"):
            parse_header("NoHeaderHere")

    def test_parse_incomplete_header(self):
        with pytest.raises(ValidationError, match="unterminated header"):
            parse_header("^b81:7:standard")

    def test_parse_malformed_header(self):
        with pytest.raises(ValidationError, match="malformed header"):
            parse_header("^b81:7standard^")

    def test_parse_invalid_block_size(self):
        with pytest.raises(ValidationError, match="block_size must be numeric"):
            parse_header("^b81:seven:standard^")

    def test_parse_unknown_codec(self):
        with pytest.raises(ValidationError, match="unknown codec"):
            parse_header("^b81:99:standard^")

    def test_parse_unknown_alphabet(self):
        with pytest.raises(ValidationError, match="unknown codec"):
            parse_header("^b81:7:unknown^")

    def test_header_too_long(self):
        # Header > 64 chars
        long_header = "^b81:" + "x" * 60 + ":standard^"
        with pytest.raises(ValidationError, match="unterminated header"):
            parse_header(long_header)


class TestHeaderRoundtrip:
    @pytest.mark.parametrize("block_size,alphabet", [
        (3, "standard"), (7, "standard"), (5, "url")
    ])
    def test_roundtrip(self, block_size, alphabet):
        header = make_header(block_size, alphabet)
        payload = "testpayload"
        full = header + payload
        bs, alpha, p = parse_header(full)
        assert bs == block_size
        assert alpha == alphabet
        assert p == payload

    def test_payload_with_header_chars(self):
        header = make_header(7, "standard")
        payload = "data^with^carets^"
        full = header + payload
        bs, alpha, p = parse_header(full)
        assert p == payload