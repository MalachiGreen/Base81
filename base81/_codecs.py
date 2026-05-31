# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Codec registry with compile-time validation.

Each codec defined by (alphabet_type, block_size):
- ("standard", 3): 3 bytes → 4 chars (81^4 ≥ 256^3)
- ("standard", 7): 7 bytes → 9 chars (81^9 ≥ 256^7) with dynamic tails
- ("url", 5): 5 bytes → 7 chars (62^7 ≥ 256^5)

Tail mappings computed dynamically for minimal char usage:
- For each remainder r (1..fn-1), find smallest k s.t. radix^k ≥ 256^r
- Ensures encoder/decoder tail lengths form a bijection

Validation checks:
- Headroom: radix^fk ≥ 256^fn (full block capacity)
- Tail bijection: te[r] = k ⇔ td[k] = r, and te covers all 1..fn-1
"""

import types
from typing import Dict, Tuple, List, Any, Mapping, Optional
from ._alphabet import ALPHABET_STANDARD, ALPHABET_URL
from ._math import POW
from ._exceptions import CodecError

_LOOKUPS: Dict[str, Dict[str, Any]] = {
    "standard": {
        "base": 81,
        "to_char": ALPHABET_STANDARD,
        "to_idx": {c: i for i, c in enumerate(ALPHABET_STANDARD)},
    },
    "url": {
        "base": 62,
        "to_char": ALPHABET_URL,
        "to_idx": {c: i for i, c in enumerate(ALPHABET_URL)},
    },
}

_CODECS: Dict[Tuple[str, int], Dict[str, Any]] = {}


def _add(alpha: str, bs: int, fn: int, fk: int,
         te: Dict[int, int], td: Dict[int, int]) -> None:
    radix = _LOOKUPS[alpha]["base"]
    if POW[radix][fk] < POW[256][fn]:
        raise CodecError("headroom fail")
    if set(te.keys()) != set(range(1, fn)) or set(td.keys()) != set(te.values()):
        raise CodecError("tail mapping fail")
    for r, k in te.items():
        if POW[radix][k] < POW[256][r] or td[k] != r:
            raise CodecError("tail bijection fail")
    _CODECS[(alpha, bs)] = {
        "radix": radix,
        "full_n": fn,
        "full_k": fk,
        "tail_enc": dict(te),
        "tail_dec": dict(td),
        "max_tail": max(td) if td else 0,
    }


# Codec: Base81, 3-byte blocks (fixed mapping, no dynamic tails needed)
_add("standard", 3, 3, 4, {1: 2, 2: 3}, {2: 1, 3: 2})

# Codec: Base81, 7-byte blocks
t7e: Dict[int, int] = {}
t7d: Dict[int, int] = {}
for r in range(1, 7):
    k = 1
    while POW[81][k] < POW[256][r]:
        k += 1
    t7e[r], t7d[k] = k, r
_add("standard", 7, 7, 9, t7e, t7d)

# Codec: Base62, 5-byte blocks
t5e: Dict[int, int] = {}
t5d: Dict[int, int] = {}
for r in range(1, 5):
    k = 1
    while POW[62][k] < POW[256][r]:
        k += 1
    t5e[r], t5d[k] = k, r
_add("url", 5, 5, 7, t5e, t5d)

CODECS: Mapping[Tuple[str, int], Dict[str, Any]] = types.MappingProxyType(_CODECS)
LOOKUPS: Mapping[str, Dict[str, Any]] = types.MappingProxyType(_LOOKUPS)


def get_codec(alpha: str, bs: int) -> Optional[Dict[str, Any]]:
    """Return codec config or None if not registered."""
    return CODECS.get((alpha, bs))


def list_codecs() -> List[Tuple[str, int]]:
    """Return list of registered (alphabet_type, block_size) tuples."""
    return list(CODECS.keys())