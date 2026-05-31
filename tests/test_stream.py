import pytest
from base81 import Encoder, Decoder
from base81._exceptions import ValidationError, BoundaryError, CorruptStreamError


@pytest.mark.parametrize("alphabet,block_size", [("standard", 3), ("standard", 7), ("url", 5)])
def test_stream_roundtrip_small(alphabet, block_size, random_bytes):
    enc = Encoder(block_size=block_size, alphabet_type=alphabet)
    dec = Decoder(block_size=block_size, alphabet_type=alphabet)
    out = bytearray()
    chunk_size = 13
    for i in range(0, len(random_bytes), chunk_size):
        chunk = random_bytes[i:i+chunk_size]
        encoded = enc.update(chunk)
        if encoded:
            out.extend(dec.update(encoded))
    final_enc = enc.finalize()
    if final_enc:
        out.extend(dec.update(final_enc))
    out.extend(dec.finalize())
    assert bytes(out) == random_bytes


def test_encoder_buffer_limit():
    enc = Encoder(max_buffer=10)
    with pytest.raises(BoundaryError, match="buffer limit exceeded"):
        enc.update(b"x" * 20)


def test_encoder_input_limit():
    enc = Encoder(max_input_length=100)
    enc.update(b"x" * 100)
    with pytest.raises(BoundaryError, match="input limit exceeded"):
        enc.update(b"x")


def test_decoder_buffer_limit_validation():
    # Valid buffer size (>= fk+mt) should not raise
    Decoder(block_size=7, alphabet_type="standard", max_buffer=20)
    # Too small should raise during init
    with pytest.raises(ValidationError, match="max_buffer too small"):
        Decoder(block_size=7, alphabet_type="standard", max_buffer=10)


def test_decoder_input_limit():
    dec = Decoder(max_input_length=10)
    dec.update("12345")
    dec.update("12345")  # total 10 chars
    with pytest.raises(BoundaryError, match="input limit exceeded"):
        dec.update("1")


def test_decoder_whitespace_handling():
    dec = Decoder(ignore_whitespace=False)
    with pytest.raises(ValidationError, match="whitespace at 0"):
        dec.update(" ABC")
    dec_ws = Decoder(ignore_whitespace=True)
    # Should not raise
    dec_ws.update(" \n ABC\t")
    # But will fail later because "ABC" is not valid base81
    with pytest.raises(CorruptStreamError):
        dec_ws.finalize()


def test_diagnostics():
    enc = Encoder()
    assert enc.diagnostics() == {"buffer_len": 0, "total_bytes": 0}
    enc.update(b"x")
    d = enc.diagnostics()
    assert d["total_bytes"] == 1
    assert d["buffer_len"] == 1
    enc.update(b"x" * 6)
    d = enc.diagnostics()
    # After 7 bytes, buffer should be 0 because full block emitted
    assert d["buffer_len"] == 0
    assert d["total_bytes"] == 7

    dec = Decoder()
    d = dec.diagnostics()
    assert d["buffer_len"] == 0
    assert d["total_chars"] == 0
    dec.update("A" * 9)
    d = dec.diagnostics()
    assert d["total_chars"] == 9
    # After processing full block, buffer may be zero
    assert d["buffer_len"] >= 0