# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Character sets for Base81 and Base62 encoding.

ALPHABET_STANDARD (81 chars): digits (0-9) + uppercase (excl I,O) + lowercase (excl l) + 22 specials
ALPHABET_URL (62 chars): digits + uppercase + lowercase (full sets, no specials)

Both alphabets exclude '^' which is reserved for header delimiter and '~' which is removed due to the alphabet's completion.
"""

ALPHABET_STANDARD = (
    "0123456789"
    "ABCDEFGHJKLMNPQRSTUVWXYZ"  # I and O excluded (visually ambiguous)
    "abcdefghijkmnopqrstuvwxyz"  # l excluded
    "!#$%&()*+-./:;=?@_{}[]"  # ^ and ~ excluded
)

ALPHABET_URL = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
)

assert len(ALPHABET_STANDARD) == 81
assert len(ALPHABET_URL) == 62
assert '^' not in ALPHABET_STANDARD and '^' not in ALPHABET_URL

_WS_REMOVE_TABLE = str.maketrans('', '', ' \t\n\r')  # for ignore_whitespace flag
