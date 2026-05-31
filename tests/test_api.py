import pytest
from base81 import encode, decode
from base81._exceptions import ValidationError, BoundaryError


@pytest.mark.parametrize("alphabet,block_size", [("standard", 3), ("standard", 7), ("url", 5)])
def test_roundtrip_empty(alphabet, block_size):
    assert decode(encode(b"", block_size=block_size, alphabet_type=alphabet),
                  block_size=block_size, alphabet_type=alphabet) == b""


@pytest.mark.parametrize("alphabet,block_size", [("standard", 3), ("standard", 7), ("url", 5)])
def test_roundtrip_single_byte(alphabet, block_size):
    for i in range(256):
        data = bytes([i])
        enc = encode(data, block_size=block_size, alphabet_type=alphabet)
        dec = decode(enc, block_size=block_size, alphabet_type=alphabet)
        assert dec == data


@pytest.mark.parametrize("alphabet,block_size", [("standard", 3), ("standard", 7), ("url", 5)])
def test_roundtrip_random_bytes(alphabet, block_size, random_bytes):
    enc = encode(random_bytes, block_size=block_size, alphabet_type=alphabet)
    dec = decode(enc, block_size=block_size, alphabet_type=alphabet)
    assert dec == random_bytes


def test_encode_invalid_type():
    with pytest.raises(TypeError, match="bytes required"):
        encode("not bytes")  # type: ignore


def test_decode_invalid_type():
    with pytest.raises(TypeError, match="str required"):
        decode(b"not string")  # type: ignore


def test_encode_invalid_codec():
    with pytest.raises(ValidationError, match="unknown codec"):
        encode(b"test", block_size=99, alphabet_type="standard")


def test_decode_whitespace_rejection():
    enc = encode(b"data")
    with pytest.raises(ValidationError, match="whitespace at 0"):
        decode(f" {enc}", ignore_whitespace=False)


def test_decode_whitespace_ignored():
    enc = encode(b"data")
    assert decode(f" {enc}\n", ignore_whitespace=True) == b"data"


def test_non_canonical_tail_validation_disabled():
    data = b"\x0a"
    enc = encode(data, block_size=7, alphabet_type="standard")
    # enc is "0A" (canonical)
    dec = decode(enc, block_size=7, alphabet_type="standard", validate_canonical=False)
    assert dec == data
    dec2 = decode(enc, block_size=7, alphabet_type="standard", validate_canonical=True)
    assert dec2 == data


def test_decode_max_input_length():
    enc = encode(b"x" * 1000)
    with pytest.raises(BoundaryError, match="input too long"):
        decode(enc, max_input_length=100)  # only 100 chars allowed


def test_encode_line_wrapping():
    data = b"x" * 100
    enc = encode(data, line_width=20)
    lines = enc.split("\n")
    assert all(len(line) <= 20 for line in lines)
    # No trailing newline
    assert not enc.endswith("\n")
    # Decode with whitespace ignore works
    assert decode(enc, ignore_whitespace=True) == data


def test_encode_line_width_invalid():
    with pytest.raises(ValidationError, match="positive int"):
        encode(b"x", line_width=0)
    with pytest.raises(ValidationError, match="positive int"):
        encode(b"x", line_width=True)  # type: ignore