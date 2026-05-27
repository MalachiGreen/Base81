# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
CLI interface and self-test harness.

Usage:
    python -m base81 encode [--block-size N] [--alphabet TYPE] [--header] [--input FILE] [--output FILE]
    python -m base81 decode [--ignore-ws] [--block-size N] [--alphabet TYPE] [--no-canonical-check] [--header] [--input FILE] [--output FILE]
    python -m base81  # runs self-test

Self-test validates:
    - Header parsing
    - Buffer limit enforcement (BoundaryError on oversized buffers)
    - Round-trip fidelity for all codec variants
    - Edge cases (empty input, partial blocks)

Run without arguments for self-test; with subcommands for encoding/decoding.
"""

import sys
import os
from ._api import encode, decode
from ._stream import Encoder, Decoder
from ._header import parse_header
from ._exceptions import ValidationError, BoundaryError

if len(sys.argv) == 1:
    print("Base81/62 v0.1.0 self-test…")

    assert parse_header(" \n \t ^b81:7:standard^payload")[2] == "payload"

    try:
        Decoder(block_size=7, alphabet_type="standard", max_buffer=True)
        raise RuntimeError("bool guard fail")
    except ValidationError:
        pass

    try:
        Decoder(block_size=7, alphabet_type="standard", max_buffer=10)
        raise RuntimeError("min buffer fail")
    except ValidationError:
        pass

    limited_enc = Encoder(max_buffer=20)
    try:
        limited_enc.update(b"1234567890123456789012345")
        raise RuntimeError("encoder buffer fail")
    except BoundaryError:
        d = limited_enc.diagnostics()
        assert d["total_bytes"] == 0
        assert d["buffer_len"] == 0

    limited_dec = Decoder(block_size=3, alphabet_type="standard", max_buffer=20)
    try:
        limited_dec.update(b"1234567890123456789012345")
        raise RuntimeError("decoder buffer fail")
    except BoundaryError:
        d = limited_dec.diagnostics()
        assert d["total_chars"] == 0
        assert d["buffer_len"] == 0

    for alpha, bs in [("standard", 7), ("standard", 3), ("url", 5)]:
        assert decode(encode(b"", block_size=bs, alphabet_type=alpha),
                      block_size=bs, alphabet_type=alpha) == b""

        enc = Encoder(block_size=bs, alphabet_type=alpha)
        dec = Decoder(block_size=bs, alphabet_type=alpha)
        payload = os.urandom(4096)
        out = bytearray()

        for i in range(0, len(payload), 53):
            tb = enc.update(payload[i:i+53])
            if tb:
                out.extend(dec.update(tb))
        tb = enc.finalize()
        if tb:
            out.extend(dec.update(tb))
        out.extend(dec.finalize())
        assert bytes(out) == payload, f"roundtrip fail {alpha}:{bs}"

    print("All checks passed. 🚀")
else:
    from ._cli import main
    main()
