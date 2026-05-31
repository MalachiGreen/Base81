# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Self-describing header format.

Format: ^b81:{block_size}:{alphabet_type}^{payload}

Example: ^b81:7:standard^ABCD123...

Parsing:
- Strips leading whitespace (tolerant of formatted files)
- Extracts block_size and alphabet_type
- Validates against registered codecs
- Returns remaining string (payload without header)

Used when --header flag is passed to CLI, allowing automatic codec detection.
"""

from typing import Tuple
from ._codecs import CODECS, LOOKUPS
from ._exceptions import ValidationError

PREFIX = "^b81:"
SUFFIX = "^"


def make_header(block_size: int, alphabet_type: str) -> str:
    """Create header string for given codec."""
    return f"{PREFIX}{block_size}:{alphabet_type}{SUFFIX}"


def parse_header(s: str) -> Tuple[int, str, str]:
    """Extract (block_size, alphabet_type, payload) from header-prefixed string."""
    stripped = s.lstrip(' \t\n\r')
    if not stripped.startswith(PREFIX):
        raise ValidationError("missing header")
    end = stripped.find(SUFFIX, len(PREFIX))
    if end == -1 or end > 64:
        raise ValidationError("unterminated header")
    meta = stripped[len(PREFIX):end]
    colon = meta.find(":")
    if colon == -1:
        raise ValidationError("malformed header")
    bs_str = meta[:colon]
    alpha = meta[colon+1:]
    if not bs_str.isdigit():
        raise ValidationError("block_size must be numeric")
    bs = int(bs_str)
    if alpha not in LOOKUPS or (alpha, bs) not in CODECS:
        raise ValidationError("unknown codec in header")
    consumed = (len(s) - len(stripped)) + end + len(SUFFIX)
    return bs, alpha, s[consumed:]