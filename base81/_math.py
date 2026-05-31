# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Arithmetic primitives for radix conversion.

Precomputed POW[base][exp] for base ∈ {62,81,100,256}, exp ≤ 16.

Functions:
- int_to_radix(value, out_len, alpha_cfg) -> string (little-endian digit order)
- radix_to_int(string, alpha_cfg, expected_len) -> int
- bytes_to_int(data) -> int (big-endian)
- int_to_bytes(value, length) -> bytes (big-endian, zero-padded)

Invariants:
- int_to_radix(radix_to_int(s, cfg, len(s)), len(s), cfg) == s
- int_to_bytes(bytes_to_int(b), len(b)) == b
- Value overflow raises CorruptStreamError before conversion
"""

import types
from typing import Dict, List, Any, Mapping
from ._exceptions import CodecError, ValidationError, CorruptStreamError


def _build(base: int, n: int) -> List[int]:
    t = [1]
    for _ in range(n):
        t.append(t[-1] * base)
    return t


_POW81: List[int] = _build(81, 16)
_POW62: List[int] = _build(62, 16)
_POW256: List[int] = _build(256, 16)

_STATIC_POW: Dict[int, List[int]] = {
    81: _POW81,
    62: _POW62,
    256: _POW256,
}
POW: Mapping[int, List[int]] = types.MappingProxyType(_STATIC_POW)


def int_to_radix(value: int, out_len: int, alpha_cfg: Dict[str, Any]) -> str:
    """Convert integer to base-N string with fixed length."""
    if value < 0:
        raise CodecError("negative value")
    radix = alpha_cfg["base"]
    if value >= POW[radix][out_len]:
        raise CorruptStreamError("overflow")
    chars: List[str] = [''] * out_len
    idx = out_len - 1
    ac = alpha_cfg["to_char"]
    while idx >= 0:
        value, rem = divmod(value, radix)
        chars[idx] = ac[rem]
        idx -= 1
    return ''.join(chars)


def radix_to_int(s: str, alpha_cfg: Dict[str, Any], expected_len: int) -> int:
    """Convert base-N string to integer, validating length and characters."""
    if len(s) != expected_len:
        raise CorruptStreamError("length mismatch")
    radix = alpha_cfg["base"]
    idx_map = alpha_cfg["to_idx"]
    val = 0
    for ch in s:
        if ch not in idx_map:
            raise ValidationError(f"character '{ch}' not in alphabet")
        val = val * radix + idx_map[ch]
    return val


def bytes_to_int(data: bytes) -> int:
    """Convert big-endian bytes to integer."""
    return int.from_bytes(data, 'big')


def int_to_bytes(value: int, length: int) -> bytes:
    """Convert integer to big-endian bytes of fixed length."""
    if value >= (1 << (8 * length)):
        raise ValueError("value too large")
    return value.to_bytes(length, 'big')