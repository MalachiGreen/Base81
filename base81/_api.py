# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Synchronous encode/decode API.

Encode:
- Takes bytes, returns string
- Supports line wrapping for readability
- Block size 3/5/7 bytes per group

Decode:
- Takes string, returns bytes
- Optional whitespace stripping (ignores \n in wrapped output)
- Canonical validation prevents ambiguous padding (like base64's = vs correct padding)
- Max input length prevents DoS

Tail canonicalization:
- For remainder bytes r (< fn), encode to k chars where 81^k ≥ 256^r
- Decode validates that k chars decode back to exactly r bytes (no leading zeros)
- Prevents malicious inputs like "A" decoding to 0x00 0x00 ... 0x01
"""

from typing import Optional
from ._codecs import CODECS, LOOKUPS
from ._math import int_to_radix, radix_to_int, bytes_to_int, int_to_bytes, POW
from ._alphabet import _WS_REMOVE_TABLE
from ._exceptions import ValidationError, CorruptStreamError, BoundaryError


def encode(data: bytes, *, line_width: Optional[int] = None,
           block_size: int = 7, alphabet_type: str = "standard") -> str:
    """Encode bytes to base-N string."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("bytes required")
    cfg = CODECS.get((alphabet_type, block_size))
    if cfg is None:
        raise ValidationError(f"unknown codec {(alphabet_type, block_size)}")

    ac = LOOKUPS[alphabet_type]
    fn, fk, te = cfg["full_n"], cfg["full_k"], cfg["tail_enc"]

    parts = []
    pos, n = 0, len(data)
    while pos + fn <= n:
        parts.append(int_to_radix(bytes_to_int(data[pos:pos+fn]), fk, ac))
        pos += fn
    if n - pos > 0:
        parts.append(int_to_radix(bytes_to_int(data[pos:]), te[n-pos], ac))

    payload = ''.join(parts)
    if line_width is not None:
        if isinstance(line_width, bool) or not isinstance(line_width, int) or line_width <= 0:
            raise ValidationError("line_width must be positive int")
        payload = '\n'.join(payload[i:i+line_width] for i in range(0, len(payload), line_width))
    return payload


def decode(s: str, *, ignore_whitespace: bool = False, validate_canonical: bool = True,
           block_size: int = 7, max_input_length: Optional[int] = None,
           alphabet_type: str = "standard") -> bytes:
    """Decode base-N string to bytes."""
    if not isinstance(s, str):
        raise TypeError("str required")
    cfg = CODECS.get((alphabet_type, block_size))
    if cfg is None:
        raise ValidationError(f"unknown codec {(alphabet_type, block_size)}")

    if max_input_length is not None:
        if isinstance(max_input_length, bool) or not isinstance(max_input_length, int) or max_input_length <= 0:
            raise ValidationError("max_input_length must be positive int")
        if len(s) > max_input_length:
            raise BoundaryError("input too long")

    if ignore_whitespace:
        s = s.translate(_WS_REMOVE_TABLE)
    else:
        for i, ch in enumerate(s):
            if ch in ' \t\n\r':
                raise ValidationError(f"whitespace at {i}")

    if not s:
        return b''

    ac = LOOKUPS[alphabet_type]
    fn, fk, td = cfg["full_n"], cfg["full_k"], cfg["tail_dec"]
    p256 = POW[256]

    total = len(s)
    out = bytearray()
    pos = 0
    limit = p256[fn]

    while pos + fk <= total:
        val = radix_to_int(s[pos:pos+fk], ac, fk)
        if val >= limit:
            raise CorruptStreamError(f"block overflow at {pos}")
        out.extend(int_to_bytes(val, fn))
        pos += fk

    remaining = total - pos
    if remaining > 0:
        if remaining not in td:
            raise CorruptStreamError(f"bad tail at {pos}")
        r = td[remaining]
        val = radix_to_int(s[pos:], ac, remaining)
        if val >= p256[r]:
            raise CorruptStreamError("tail overflow")
        tail_res = int_to_bytes(val, r)
        if validate_canonical:
            expected = int_to_radix(bytes_to_int(tail_res), remaining, ac)
            if s[-remaining:] != expected:
                raise ValidationError("non-canonical tail")
        out.extend(tail_res)

    return bytes(out)