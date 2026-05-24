# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

import sys
import argparse
from ._api import encode, decode
from ._header import make_header, parse_header
from ._exceptions import CorruptStreamError


def main():
    parser = argparse.ArgumentParser(description="Base81/62 v0.1.0")
    sub = parser.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encode")
    enc.add_argument("--line-width", type=int, default=None)
    enc.add_argument("--block-size", type=int, default=7, choices=[3, 5, 7])
    enc.add_argument("--alphabet", choices=["standard", "url"], default="standard")
    enc.add_argument("--header", action="store_true")
    enc.add_argument("--input", "-i")
    enc.add_argument("--output", "-o")

    dec = sub.add_parser("decode")
    dec.add_argument("--ignore-ws", action="store_true")
    dec.add_argument("--block-size", type=int, default=7, choices=[3, 5, 7])
    dec.add_argument("--alphabet", choices=["standard", "url"], default="standard")
    dec.add_argument("--no-canonical-check", action="store_true")
    dec.add_argument("--header", action="store_true")
    dec.add_argument("--max-input-length", type=int, default=None)
    dec.add_argument("--input", "-i")
    dec.add_argument("--output", "-o")

    args = parser.parse_args()

    if args.cmd == "encode":
        inp = open(args.input, "rb") if args.input else sys.stdin.buffer
        out = open(args.output, "w") if args.output else sys.stdout
        try:
            data = inp.read()
            result = encode(data, line_width=args.line_width,
                            block_size=args.block_size, alphabet_type=args.alphabet)
            if args.header:
                result = make_header(args.block_size, args.alphabet) + result
            out.write(result)
        finally:
            if args.input: inp.close()
            if args.output: out.close()
    else:
        inp = open(args.input, "rb") if args.input else sys.stdin.buffer
        out = open(args.output, "wb") if args.output else sys.stdout.buffer
        try:
            raw = inp.read()
            try:
                text = raw.decode('ascii')
            except UnicodeDecodeError:
                raise CorruptStreamError("non-ASCII input")
            alpha = args.alphabet
            bs = args.block_size
            if args.header:
                bs, alpha, text = parse_header(text)
            result = decode(text, ignore_whitespace=args.ignore_ws,
                            validate_canonical=not args.no_canonical_check,
                            block_size=bs, max_input_length=args.max_input_length,
                            alphabet_type=alpha)
            out.write(result)
        finally:
            if args.input: inp.close()
            if args.output: out.close()