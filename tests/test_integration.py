"""Integration tests combining multiple components."""

import pytest
import os
import tempfile
from base81 import encode, decode, Encoder, Decoder, make_header, parse_header


class TestFullWorkflows:
    def test_file_roundtrip_with_header(self):
        """Simulate file encoding/decoding with header."""
        original = os.urandom(1024 * 100)  # 100KB
        
        # Encode with header
        encoded = make_header(7, "standard") + encode(original, block_size=7)
        
        # Simulate file write/read
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(encoded)
            f_path = f.name
        
        try:
            # Read and decode with header
            with open(f_path, 'r') as f:
                content = f.read()
            bs, alpha, payload = parse_header(content)
            decoded = decode(payload, block_size=bs, alphabet_type=alpha)
            assert decoded == original
        finally:
            os.unlink(f_path)

    def test_streaming_large_file(self):
        """Process large file without loading entirely into memory."""
        original = os.urandom(1024 * 1024)  # 1MB
        
        # Streaming encode
        enc = Encoder(block_size=7, max_buffer=65536)
        chunks = [original[i:i+8192] for i in range(0, len(original), 8192)]
        
        encoded_parts = []
        for chunk in chunks:
            encoded_parts.append(enc.update(chunk))
        encoded_parts.append(enc.finalize())
        encoded = ''.join(encoded_parts)
        
        # Streaming decode
        dec = Decoder(block_size=7, max_buffer=65536)
        decoded_parts = []
        for i in range(0, len(encoded), 8192):
            decoded_parts.append(dec.update(encoded[i:i+8192]))
        decoded_parts.append(dec.finalize())
        decoded = b''.join(decoded_parts)
        
        assert decoded == original

    def test_malformed_input_recovery(self):
        """System should reject malformed input clearly."""
        valid = encode(b"test data")
        
        # Corrupt in various ways
        corruptions = [
            valid.replace('a', '$'),  # Invalid char
            valid + 'extra',           # Extra chars
            valid[:-5],                # Truncated
            '^b81:7:standard^' + valid,  # Unexpected header
        ]
        
        for corrupted in corruptions:
            with pytest.raises(Exception):  # Should raise some CodecError
                decode(corrupted)

    def test_concurrent_encoders(self):
        """Multiple encoders/decoders should not interfere."""
        data1 = b"Stream 1 data " * 100
        data2 = b"Stream 2 data " * 100
        
        enc1 = Encoder(block_size=7)
        enc2 = Encoder(block_size=7)
        
        out1 = enc1.update(data1[:500]) + enc1.update(data1[500:]) + enc1.finalize()
        out2 = enc2.update(data2[:500]) + enc2.update(data2[500:]) + enc2.finalize()
        
        dec1 = Decoder(block_size=7)
        dec2 = Decoder(block_size=7)
        
        result1 = dec1.update(out1) + dec1.finalize()
        result2 = dec2.update(out2) + dec2.finalize()
        
        assert result1 == data1
        assert result2 == data2


class TestEdgeCasesIntegration:
    def test_all_zero_bytes(self):
        data = b'\x00' * 1000
        for bs, alpha in [(3, "standard"), (7, "standard"), (5, "url")]:
            encoded = encode(data, block_size=bs, alphabet_type=alpha)
            # Should encode to repeated '0' chars (first alphabet char)
            assert all(ch == '0' for ch in encoded)
            decoded = decode(encoded, block_size=bs, alphabet_type=alpha)
            assert decoded == data

    def test_all_max_bytes(self):
        data = b'\xff' * 1000
        for bs, alpha in [(3, "standard"), (7, "standard"), (5, "url")]:
            encoded = encode(data, block_size=bs, alphabet_type=alpha)
            decoded = decode(encoded, block_size=bs, alphabet_type=alpha)
            assert decoded == data

    def test_alternating_bytes(self):
        data = bytes([i % 256 for i in range(1000)])
        for bs, alpha in [(3, "standard"), (7, "standard"), (5, "url")]:
            encoded = encode(data, block_size=bs, alphabet_type=alpha)
            decoded = decode(encoded, block_size=bs, alphabet_type=alpha)
            assert decoded == data

    def test_boundary_conditions(self):
        """Test sizes just at block boundaries."""
        sizes = [0, 1, 2, 3, 4, 5, 6, 7, 8, 13, 14, 20, 21]
        for size in sizes:
            data = os.urandom(size)
            for bs, alpha in [(3, "standard"), (7, "standard"), (5, "url")]:
                if bs == 5 and alpha != "url":
                    continue
                encoded = encode(data, block_size=bs, alphabet_type=alpha)
                decoded = decode(encoded, block_size=bs, alphabet_type=alpha)
                assert decoded == data

    def test_max_buffer_exact(self):
        """Test that max_buffer exactly at fk+mt works."""
        dec = Decoder(block_size=7, max_buffer=15)  # fk=9, mt=6
        encoded = encode(b"test")
        result = dec.update(encoded) + dec.finalize()
        assert result == b"test"

    def test_very_large_buffer_allowed(self):
        """Large buffer should work without performance issues."""
        enc = Encoder(max_buffer=100 * 1024 * 1024)  # 100MB
        data = os.urandom(1024 * 1024)  # 1MB
        result = enc.update(data) + enc.finalize()
        assert len(result) > 0


class TestPerformance:
    @pytest.mark.slow
    def test_encode_throughput(self):
        """Verify acceptable performance (not strict benchmark)."""
        import time
        data = os.urandom(10 * 1024 * 1024)  # 10MB
        
        start = time.time()
        encode(data, block_size=7)
        elapsed = time.time() - start
        
        # Should encode at least 50MB/s on reasonable hardware
        assert elapsed < 0.2  # 10MB in 0.2s = 50MB/s

    @pytest.mark.slow
    def test_decode_throughput(self):
        import time
        data = os.urandom(10 * 1024 * 1024)
        encoded = encode(data, block_size=7)
        
        start = time.time()
        decode(encoded, block_size=7)
        elapsed = time.time() - start
        
        assert elapsed < 0.3  # Slightly slower than encode due to validation