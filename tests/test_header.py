import pytest
from base81 import make_header, parse_header
from base81._exceptions import ValidationError


def test_make_header():
    assert make_header(7, "standard") == "^b81:7:standard^"
    assert make_header(5, "url") == "^b81:5:url^"


def test_parse_header_valid():
    full = "^b81:7:standard^ABCD"
    bs, alpha, payload = parse_header(full)
    assert bs == 7
    assert alpha == "standard"
    assert payload == "ABCD"


def test_parse_header_ignores_leading_whitespace():
    full = " \n\t^b81:3:standard^XYZ"
    bs, alpha, payload = parse_header(full)
    assert bs == 3
    assert alpha == "standard"
    assert payload == "XYZ"


def test_parse_header_missing():
    with pytest.raises(ValidationError, match="missing header"):
        parse_header("no header here")


def test_parse_header_unterminated():
    with pytest.raises(ValidationError, match="unterminated header"):
        parse_header("^b81:7:standard")


def test_parse_header_malformed():
    with pytest.raises(ValidationError, match="malformed header"):
        parse_header("^b81:7standard^")
    with pytest.raises(ValidationError, match="block_size must be numeric"):
        parse_header("^b81:seven:standard^")


def test_parse_header_unknown_codec():
    with pytest.raises(ValidationError, match="unknown codec in header"):
        parse_header("^b81:99:standard^")
    with pytest.raises(ValidationError, match="unknown codec in header"):
        parse_header("^b81:7:unknown^")


def test_parse_header_payload_after_header():
    full = "^b81:5:url^ThePayload"
    _, _, payload = parse_header(full)
    assert payload == "ThePayload"
    # Ensure exactly the suffix after header is returned
    assert parse_header("^b81:5:url^^")[2] == "^"