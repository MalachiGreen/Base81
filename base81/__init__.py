# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Base81/62 – Multi-Radix Binary-to-Text Codec.

Provides encoding/decoding with 81-character (full ASCII printable) and
62-character (URL-safe) alphabets.

Quick start:
    from base81 import encode, decode
    
    data = b"Hello World"
    encoded = encode(data, block_size=7, alphabet_type="standard")
    decoded = decode(encoded, block_size=7, alphabet_type="standard")
    assert decoded == data

Block size trade-offs:
    - block_size=3: 3 bytes → 4 chars (fixed, no tail variants)
    - block_size=7: 7 bytes → 9 chars typical, 1-6 byte tails use 2-8 chars
    - block_size=5: only for url alphabet, 5 bytes → 7 chars

Streaming:
    enc = Encoder(block_size=7, max_buffer=1024*1024)
    enc.update(b"chunk1")
    enc.update(b"chunk2")
    result = enc.finalize()

Memory limits:
    - max_input_length: total bytes (encoder) or chars (decoder)
    - max_buffer: pending data before forced flush
    - BoundaryError raised on exceed, state accessible via diagnostics()

See individual modules for details:
    _api      - synchronous encode/decode
    _stream   - streaming Encoder/Decoder
    _codecs   - codec registry and validation
    _math     - radix conversion primitives
    _header   - self-describing header format
    _exceptions - error hierarchy
"""

from ._alphabet import ALPHABET_STANDARD, ALPHABET_URL
from ._codecs import get_codec, list_codecs
from ._exceptions import CodecError, ValidationError, CorruptStreamError, BoundaryError
from ._api import encode, decode
from ._stream import Encoder, Decoder

__all__ = [
    "encode", "decode", "Encoder", "Decoder",
    "CodecError", "ValidationError", "CorruptStreamError", "BoundaryError",
    "ALPHABET_STANDARD", "ALPHABET_URL",
    "get_codec", "list_codecs",
]
__version__ = "0.1.0"
