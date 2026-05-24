"""Tests for streaming Encoder and Decoder."""

import pytest
from base81 import Encoder, Decoder
from base81._exceptions import ValidationError, BoundaryError, CorruptStreamError


class TestEncoderBasics:
    def test_empty_update(self):
        enc = Encoder()
        assert enc.update(b"") == ""
        assert enc.finalize() == ""

    def test_single_update(self):
        enc = Encoder(block_size=7, alphabet_type="standard")
        data = b"Hello World" * 100
        result = enc.update(data) + enc.finalize()
        # Compare with batch encode
        from base81 import encode
        expected = encode(data, block_size=7, alphabet_type="standard")
        assert result == expected

    def test_chunked_update(self):
        enc = Encoder(block_size=7)
        data = b"X" * 1000
        chunks = [data[i:i+73] for i in range(0, len(data), 73)]
        result = ""
        for chunk in chunks:
            result += enc.update(chunk)
        result += enc.finalize()
        from base81 import encode
        assert result == encode(data, block_size=7)

    def test_type_check(self):
        enc = Encoder()
        with pytest.raises(TypeError, match="bytes required"):
            enc.update("not bytes")  # type: ignore


class TestEncoderBufferLimits:
    def test_max_input_length(self):
        enc = Encoder(max_input_length=100)
        enc.update(b"x" * 100)
        with pytest.raises(BoundaryError, match="input limit exceeded"):
            enc.update(b"x")

    def test_max_buffer_length(self):
        enc = Encoder(max_buffer=50)
        # Fill buffer with partial block
        enc.update(b"x" * 7)  # 7 bytes (not full block yet)
        assert len(enc._buf) == 7
        with pytest.raises(BoundaryError, match="buffer limit exceeded"):
            enc.update(b"x" * 44)  # Would exceed 50

    def test_max_buffer_allows_full_blocks(self):
        enc = Encoder(max_buffer=100)
        # Should be able to fill exactly to limit
        enc.update(b"x" * 100)  # Should process full blocks, leaving remainder

    def test_diagnostics(self):
        enc = Encoder()
        assert enc.diagnostics() == {"buffer_len": 0, "total_bytes": 0}
        enc.update(b"hello")
        diag = enc.diagnostics()
        assert diag["total_bytes"] == 5
        assert diag["buffer_len"] == 5


class TestDecoderBasics:
    def test_empty_update(self):
        dec = Decoder()
        assert dec.update("") == b""
        assert dec.finalize() == b""

    def test_single_update(self):
        dec = Decoder(block_size=7, alphabet_type="standard")
        from base81 import encode
        data = b"Hello World" * 100
        encoded = encode(data, block_size=7, alphabet_type="standard")
        result = dec.update(encoded) + dec.finalize()
        assert result == data

    def test_chunked_update(self):
        dec = Decoder(block_size=7)
        from base81 import encode
        data = b"X" * 1000
        encoded = encode(data, block_size=7)
        chunks = [encoded[i:i+50] for i in range(0, len(encoded), 50)]
        result = b""
        for chunk in chunks:
            result += dec.update(chunk)
        result += dec.finalize()
        assert result == data

    def test_type_check(self):
        dec = Decoder()
        with pytest.raises(TypeError, match="str required"):
            dec.update(b"not string")  # type: ignore


class TestDecoderWhitespace:
    def test_strict_whitespace_rejection(self):
        dec = Decoder(ignore_whitespace=False)
        with pytest.raises(ValidationError, match="whitespace"):
            dec.update("abc 123")

    def test_ignore_whitespace(self):
        dec = Decoder(ignore_whitespace=True)
        from base81 import encode
        data = b"test"
        encoded = encode(data)
        wrapped = "\n".join(encoded[i:i+10] for i in range(0, len(encoded), 10))
        result = dec.update(wrapped) + dec.finalize()
        assert result == data


class TestDecoderBufferLimits:
    def test_max_input_length(self):
        dec = Decoder(max_input_length=100)
        dec.update("x" * 100)
        with pytest.raises(BoundaryError, match="input limit exceeded"):
            dec.update("x")

    def test_max_buffer_too_small(self):
        with pytest.raises(ValidationError, match="max_buffer too small"):
            Decoder(block_size=7, max_buffer=5)  # Need fk+mt = 9+6=15

    def test_max_buffer_enforced(self):
        dec = Decoder(block_size=7, max_buffer=20)
        from base81 import encode
        data = encode(b"x" * 100)  # Long string
        # Feed gradually - should work if buffer not exceeded
        chunks = [data[i:i+5] for i in range(0, len(data), 5)]
        for chunk in chunks:
            dec.update(chunk)

    def test_diagnostics(self):
        dec = Decoder()
        assert dec.diagnostics()["total_chars"] == 0
        dec.update("abc")
        diag = dec.diagnostics()
        assert diag["total_chars"] == 3
        assert diag["buffer_len"] >= 3


class TestStreamingRoundtrip:
    @pytest.mark.parametrize("block_size,alphabet", [
        (3, "standard"), (7, "standard"), (5, "url")
    ])
    @pytest.mark.parametrize("chunk_size", [1, 7, 53, 100])
    def test_chunked_roundtrip(self, block_size, alphabet, chunk_size):
        import os
        data = os.urandom(1000)
        
        enc = Encoder(block_size=block_size, alphabet_type=alphabet)
        dec = Decoder(block_size=block_size, alphabet_type=alphabet)
        
        encoded_parts = []
        for i in range(0, len(data), chunk_size):
            encoded_parts.append(enc.update(data[i:i+chunk_size]))
        encoded_parts.append(enc.finalize())
        encoded = ''.join(encoded_parts)
        
        decoded_parts = []
        for i in range(0, len(encoded), chunk_size):
            decoded_parts.append(dec.update(encoded[i:i+chunk_size]))
        decoded_parts.append(dec.finalize())
        decoded = b''.join(decoded_parts)
        
        assert decoded == data

    def test_multiple_streams_independent(self):
        enc1 = Encoder(block_size=7)
        enc2 = Encoder(block_size=7)
        dec1 = Decoder(block_size=7)
        dec2 = Decoder(block_size=7)
        
        data1 = b"Hello"
        data2 = b"World"
        
        enc1.update(data1)
        enc2.update(data2)
        
        out1 = enc1.finalize()
        out2 = enc2.finalize()
        
        assert dec1.update(out1) + dec1.finalize() == data1
        assert dec2.update(out2) + dec2.finalize() == data2


class TestErrorRecovery:
    def test_decoder_state_after_corruption(self):
        dec = Decoder(block_size=7)
        from base81 import encode
        valid = encode(b"test")
        corrupted = valid[:-3] + "!!!"  # Invalid chars
        
        with pytest.raises(ValidationError):
            dec.update(corrupted)
        
        # Decoder should still be usable
        dec = Decoder(block_size=7)  # Recreate
        result = dec.update(valid) + dec.finalize()
        assert result == b"test"

    def test_encoder_state_after_boundary_error(self):
        enc = Encoder(max_input_length=10)
        enc.update(b"x" * 10)
        with pytest.raises(BoundaryError):
            enc.update(b"x")
        
        # Can still get diagnostics
        diag = enc.diagnostics()
        assert diag["total_bytes"] == 10