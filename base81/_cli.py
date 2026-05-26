#!/usr/bin/env python3
# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Base81/62 CLI - Binary-to-text encoding with maximum density.

Examples:
  # Basic usage
  base81 encode data.bin                    # Encode to stdout
  base81 decode data.b81                    # Decode to stdout
  base81 encode -i data.bin -o data.b81     # File to file
  
  # With headers (auto-detection)
  base81 encode --header data.bin | base81 decode --header > restored.bin
  
  # Streaming (avoid memory issues)
  base81 encode --stream < large.bin > large.b81
  cat large.bin | base81 encode --stream -w 80 > large.b81
  
  # Performance tuning
  base81 encode --block-size 7 --alphabet standard --jobs 4 data.bin
"""

import sys
import argparse
import signal
import time
import os
from typing import Optional, BinaryIO, TextIO
from contextlib import contextmanager
from ._api import encode, decode
from ._header import make_header, parse_header
from ._exceptions import CorruptStreamError, ValidationError, BoundaryError

__all__ = ["main"]

# Version from package
__version__ = "0.1.0"


@contextmanager
def _open_input(path: Optional[str], binary: bool = True):
    """Context manager for input file/stdin."""
    if not path or path == "-":
        if binary:
            yield sys.stdin.buffer
        else:
            yield sys.stdin
    else:
        mode = "rb" if binary else "r"
        with open(path, mode) as f:
            yield f


@contextmanager
def _open_output(path: Optional[str], binary: bool = True):
    """Context manager for output file/stdout."""
    if not path or path == "-":
        if binary:
            yield sys.stdout.buffer
        else:
            yield sys.stdout
    else:
        mode = "wb" if binary else "w"
        with open(path, mode) as f:
            yield f


class ProgressIndicator:
    """Simple progress indicator for large files."""
    
    def __init__(self, total: Optional[int] = None, quiet: bool = False):
        self.total = total
        self.processed = 0
        self.quiet = quiet
        self.start_time = time.time()
        self._last_update = 0
    
    def update(self, delta: int):
        """Update progress."""
        if self.quiet:
            return
        self.processed += delta
        now = time.time()
        if now - self._last_update > 0.5 or self.processed == self.total:
            self._last_update = now
            self._display()
    
    def _display(self):
        """Display progress bar."""
        if self.total:
            pct = (self.processed / self.total) * 100
            elapsed = time.time() - self.start_time
            speed = self.processed / elapsed if elapsed > 0 else 0
            sys.stderr.write(
                f"\r\x1b[KProgress: {self.processed}/{self.total} bytes "
                f"({pct:.1f}%) | {speed/1024:.1f} KB/s"
            )
        else:
            elapsed = time.time() - self.start_time
            speed = self.processed / elapsed if elapsed > 0 else 0
            sys.stderr.write(
                f"\r\x1b[KProcessed: {self.processed/1024:.1f} KB "
                f"({speed/1024:.1f} KB/s)"
            )
        if self.processed == self.total:
            sys.stderr.write("\n")
    
    def finish(self):
        """Final update."""
        if not self.quiet and self.processed > 0:
            self._display()


def _get_file_size(path: Optional[str]) -> Optional[int]:
    """Get file size for progress indicator."""
    if path and path != "-" and os.path.exists(path):
        return os.path.getsize(path)
    return None


class StreamingEncoder:
    """Streaming encoder for large files."""
    
    def __init__(self, block_size: int = 7, alphabet_type: str = "standard",
                 line_width: Optional[int] = None, buffer_size: int = 64 * 1024):
        from ._stream import Encoder
        self._encoder = Encoder(block_size=block_size, alphabet_type=alphabet_type)
        self.line_width = line_width
        self.buffer_size = buffer_size
        self._line_buffer = []
        self._line_len = 0
    
    def encode_chunk(self, chunk: bytes) -> str:
        """Encode a chunk and return output."""
        return self._encoder.update(chunk)
    
    def finalize(self) -> str:
        """Finalize encoding."""
        return self._encoder.finalize()
    
    def _apply_line_wrapping(self, text: str) -> str:
        """Apply line wrapping to output."""
        if not self.line_width:
            return text
        
        result = []
        for ch in text:
            self._line_buffer.append(ch)
            self._line_len += 1
            if self._line_len >= self.line_width:
                result.append(''.join(self._line_buffer))
                self._line_buffer = []
                self._line_len = 0
        return '\n'.join(result)
    
    def encode_stream(self, input_file: BinaryIO, output_file: TextIO,
                      progress: Optional[ProgressIndicator] = None):
        """Encode streaming with progress."""
        while True:
            chunk = input_file.read(self.buffer_size)
            if not chunk:
                break
            if progress:
                progress.update(len(chunk))
            output = self.encode_chunk(chunk)
            if output:
                wrapped = self._apply_line_wrapping(output)
                if wrapped:
                    output_file.write(wrapped)
                    if self.line_width:
                        output_file.write('\n')
        
        final = self.finalize()
        if final:
            wrapped = self._apply_line_wrapping(final)
            output_file.write(wrapped)
            if self.line_width and wrapped:
                output_file.write('\n')
        if progress:
            progress.finish()


class StreamingDecoder:
    """Streaming decoder for large files."""
    
    def __init__(self, block_size: int = 7, alphabet_type: str = "standard",
                 ignore_whitespace: bool = False, validate_canonical: bool = True,
                 buffer_size: int = 64 * 1024):
        from ._stream import Decoder
        self._decoder = Decoder(
            block_size=block_size,
            alphabet_type=alphabet_type,
            ignore_whitespace=ignore_whitespace,
            validate_canonical=validate_canonical
        )
        self.buffer_size = buffer_size
    
    def decode_chunk(self, chunk: str) -> bytes:
        """Decode a chunk."""
        return self._decoder.update(chunk)
    
    def finalize(self) -> bytes:
        """Finalize decoding."""
        return self._decoder.finalize()
    
    def decode_stream(self, input_file: TextIO, output_file: BinaryIO,
                      progress: Optional[ProgressIndicator] = None):
        """Decode streaming with progress."""
        while True:
            chunk = input_file.read(self.buffer_size)
            if not chunk:
                break
            if progress:
                progress.update(len(chunk))
            output = self.decode_chunk(chunk)
            if output:
                output_file.write(output)
        
        final = self.finalize()
        if final:
            output_file.write(final)
        if progress:
            progress.finish()


def _create_parser():
    """Create argument parser with rich help."""
    parser = argparse.ArgumentParser(
        prog="base81",
        description="Binary-to-text encoding with 81/62 character alphabets",
        epilog="""
Examples:
  # Basic encoding/decoding
  base81 encode document.pdf
  base81 decode document.b81 -o restored.pdf
  
  # Use self-describing headers (auto-detection)
  base81 encode --header data.bin | base81 decode --header > restored.bin
  
  # Stream large files (avoid memory issues)
  base81 encode --stream huge_video.mp4 -o video.b81
  cat huge_video.mp4 | base81 encode --stream -w 80 > video.b81
  
  # Multiple files
  base81 encode *.bin -o archive.b81
  base81 decode *.b81 -d restored/
  
  # Performance
  base81 encode --block-size 7 --alphabet standard --jobs 4 data.bin
  base81 encode --benchmark data.bin

For more information: https://github.com/MalachiGreen/Base81
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    
    # Global options
    parser.add_argument("--version", action="version", version=f"base81 {__version__}")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase verbosity (-v, -vv, -vvv)")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Suppress all non-error output")
    
    sub = parser.add_subparsers(dest="cmd", required=True, help="Operation to perform")
    
    # Encode command
    enc = sub.add_parser(
        "encode",
        help="Encode binary data to base81/62 text",
        aliases=["enc", "e"],
        description="""
Encode binary data to printable ASCII using base81 (dense) or base62 (URL-safe).

Block size recommendations:
  - 7 (standard): Best density, use for most cases
  - 3 (standard): Legacy/fixed mapping, 3→4 chars
  - 5 (url):      URL-safe encoding, 5→7 chars
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Input/output
    enc.add_argument("inputs", nargs="*", help="Input files (omit for stdin)")
    enc.add_argument("-i", "--input", help="Single input file (alternative syntax)")
    enc.add_argument("-o", "--output", help="Output file (default: stdout)")
    enc.add_argument("-d", "--output-dir", help="Output directory for multiple files")
    enc.add_argument("-f", "--force", action="store_true",
                     help="Overwrite output files without asking")
    
    # Encoding options
    enc.add_argument("-w", "--line-width", type=int, metavar="COLS",
                     help="Wrap output at COLS characters")
    enc.add_argument("-b", "--block-size", type=int, default=7, choices=[3, 5, 7],
                     help="Bytes per block (default: 7)")
    enc.add_argument("-a", "--alphabet", choices=["standard", "url"], default="standard",
                     help="Alphabet type (default: standard)")
    enc.add_argument("-H", "--header", action="store_true",
                     help="Prepend self-describing header")
    
    # Performance
    enc.add_argument("-s", "--stream", action="store_true",
                     help="Streaming mode (constant memory)")
    enc.add_argument("--buffer-size", type=int, default=65536, metavar="BYTES",
                     help="Buffer size for streaming (default: 64KB)")
    enc.add_argument("-j", "--jobs", type=int, default=1,
                     help="Parallel jobs for multiple files (default: 1)")
    enc.add_argument("--benchmark", action="store_true",
                     help="Run benchmark and exit")
    
    # Decode command
    dec = sub.add_parser(
        "decode",
        help="Decode base81/62 text to binary",
        aliases=["dec", "d"],
        description="""
Decode base81/62 text back to original binary data.

Auto-detection:
  Use --header to read the codec from ^b81:N:type^ prefix
  Otherwise specify --block-size and --alphabet manually
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Input/output
    dec.add_argument("inputs", nargs="*", help="Input files (omit for stdin)")
    dec.add_argument("-i", "--input", help="Single input file (alternative syntax)")
    dec.add_argument("-o", "--output", help="Output file (default: stdout)")
    dec.add_argument("-d", "--output-dir", help="Output directory for multiple files")
    dec.add_argument("-f", "--force", action="store_true",
                     help="Overwrite output files without asking")
    
    # Decoding options
    dec.add_argument("-b", "--block-size", type=int, choices=[3, 5, 7],
                     help="Override codec detection")
    dec.add_argument("-a", "--alphabet", choices=["standard", "url"],
                     help="Override codec detection")
    dec.add_argument("-H", "--header", action="store_true",
                     help="Parse header for auto-detection")
    dec.add_argument("--ignore-ws", action="store_true",
                     help="Strip whitespace from input")
    dec.add_argument("--no-canonical-check", action="store_true",
                     help="Disable tail validation (NOT recommended)")
    dec.add_argument("-m", "--max-input-length", type=int, metavar="CHARS",
                     help="Reject inputs longer than CHARS")
    
    # Performance
    dec.add_argument("-s", "--stream", action="store_true",
                     help="Streaming mode (constant memory)")
    dec.add_argument("--buffer-size", type=int, default=65536, metavar="BYTES",
                     help="Buffer size for streaming (default: 64KB)")
    
    # Info command
    info = sub.add_parser(
        "info",
        help="Show codec information",
        aliases=["show", "status"],
    )
    info.add_argument("file", nargs="?", help="Optional file to analyze")
    
    return parser


def cmd_encode(args):
    """Handle encode command."""
    # Determine input files
    inputs = args.inputs if args.inputs else []
    if args.input:
        inputs.append(args.input)
    if not inputs and not sys.stdin.isatty():
        inputs = ["-"]  # stdin
    
    if not inputs:
        print("base81: error: no input files specified (use - for stdin)", file=sys.stderr)
        return 1
    
    # Multiple files handling
    if len(inputs) > 1 and args.output and not args.output_dir:
        print("base81: error: with multiple inputs, use -d/--output-dir", file=sys.stderr)
        return 1
    
    # Parallel processing for multiple files
    if args.jobs > 1 and len(inputs) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        
        def encode_file(inpath):
            with _open_input(inpath) as f:
                data = f.read()
            result = encode(data, block_size=args.block_size,
                          alphabet_type=args.alphabet, line_width=args.line_width)
            if args.header:
                result = make_header(args.block_size, args.alphabet) + result
            return inpath, result
        
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(encode_file, inpath): inpath for inpath in inputs}
            for future in as_completed(futures):
                inpath, result = future.result()
                if args.output_dir:
                    outpath = os.path.join(args.output_dir, os.path.basename(inpath) + ".b81")
                    if not args.force and os.path.exists(outpath):
                        print(f"base81: {outpath} exists (use -f to overwrite)", file=sys.stderr)
                        return 1
                    with open(outpath, "w") as f:
                        f.write(result)
                else:
                    print(f"# {inpath}")
                    print(result)
        return 0
    
    # Single file or stdin
    input_path = inputs[0]
    total_size = _get_file_size(input_path) if input_path != "-" else None
    progress = ProgressIndicator(total=total_size, quiet=args.quiet)
    
    try:
        if args.stream and total_size and total_size > 10 * 1024 * 1024:  # >10MB
            # Streaming mode
            encoder = StreamingEncoder(
                block_size=args.block_size,
                alphabet_type=args.alphabet,
                line_width=args.line_width,
                buffer_size=args.buffer_size
            )
            with _open_input(input_path) as inf:
                with _open_output(args.output, binary=False) as outf:
                    encoder.encode_stream(inf, outf, progress)
        else:
            # Batch mode
            with _open_input(input_path) as f:
                data = f.read()
            progress.update(len(data))
            result = encode(data, block_size=args.block_size,
                          alphabet_type=args.alphabet, line_width=args.line_width)
            if args.header:
                result = make_header(args.block_size, args.alphabet) + result
            with _open_output(args.output, binary=False) as outf:
                outf.write(result)
                if not result.endswith('\n'):
                    outf.write('\n')
            progress.finish()
        return 0
    except (ValidationError, CorruptStreamError, BoundaryError) as e:
        if not args.quiet:
            print(f"base81: error: {e}", file=sys.stderr)
        return 1


def cmd_decode(args):
    """Handle decode command."""
    inputs = args.inputs if args.inputs else []
    if args.input:
        inputs.append(args.input)
    if not inputs and not sys.stdin.isatty():
        inputs = ["-"]
    
    if not inputs:
        print("base81: error: no input files specified", file=sys.stderr)
        return 1
    
    if len(inputs) > 1 and args.output and not args.output_dir:
        print("base81: error: with multiple inputs, use -d/--output-dir", file=sys.stderr)
        return 1
    
    input_path = inputs[0]
    total_size = _get_file_size(input_path) if input_path != "-" else None
    progress = ProgressIndicator(total=total_size, quiet=args.quiet)
    
    try:
        with _open_input(input_path, binary=False) as f:
            if args.stream and total_size and total_size > 1024 * 1024:  # >1MB
                # Streaming mode
                decoder = StreamingDecoder(
                    block_size=args.block_size or 7,
                    alphabet_type=args.alphabet or "standard",
                    ignore_whitespace=args.ignore_ws,
                    validate_canonical=not args.no_canonical_check,
                    buffer_size=args.buffer_size
                )
                
                # Handle header detection
                first_chunk = f.read(1024)
                remaining = f.read()
                text = first_chunk + remaining
                
                if args.header:
                    bs, alpha, payload = parse_header(text)
                    decoder = StreamingDecoder(
                        block_size=bs,
                        alphabet_type=alpha,
                        ignore_whitespace=args.ignore_ws,
                        validate_canonical=not args.no_canonical_check,
                        buffer_size=args.buffer_size
                    )
                    text = payload
                
                with _open_output(args.output, binary=True) as outf:
                    decoder.decode_stream(iter([text]), outf, progress)
            else:
                # Batch mode
                text = f.read()
                progress.update(len(text))
                
                bs = args.block_size
                alpha = args.alphabet
                payload = text
                
                if args.header:
                    bs, alpha, payload = parse_header(text)
                
                if bs is None or alpha is None:
                    if not args.quiet:
                        print("base81: error: missing block-size/alphabet (use -b/-a or --header)", 
                              file=sys.stderr)
                    return 1
                
                result = decode(payload, ignore_whitespace=args.ignore_ws,
                              validate_canonical=not args.no_canonical_check,
                              block_size=bs, max_input_length=args.max_input_length,
                              alphabet_type=alpha)
                
                with _open_output(args.output, binary=True) as outf:
                    outf.write(result)
                progress.finish()
        return 0
    except (ValidationError, CorruptStreamError, BoundaryError, UnicodeDecodeError) as e:
        if not args.quiet:
            print(f"base81: error: {e}", file=sys.stderr)
        return 1


def cmd_info(args):
    """Show codec information."""
    from ._codecs import list_codecs, CODECS
    
    print(f"base81 {__version__}")
    print(f"Python {sys.version}")
    print()
    print("Registered codecs:")
    for alpha, bs in list_codecs():
        cfg = CODECS[(alpha, bs)]
        radix = cfg["radix"]
        fn, fk = cfg["full_n"], cfg["full_k"]
        efficiency = (fn * 8) / (fk * (radix.bit_length() - 1)) * 100
        print(f"  {alpha}/{bs}: {fn}→{fk} chars | {radix}^({fk}) ≥ 256^{fn} | {efficiency:.1f}%")
    
    if args.file:
        try:
            with open(args.file, "r") as f:
                first_line = f.readline()[:200]
            if first_line.startswith("^b81:"):
                import re
                match = re.match(r'\^b81:(\d+):(\w+)\^', first_line)
                if match:
                    bs, alpha = match.groups()
                    print(f"\n{args.file} has header: block_size={bs}, alphabet={alpha}")
                else:
                    print(f"\n{args.file}: invalid header format")
            else:
                print(f"\n{args.file}: no header (first 200 chars: {first_line[:50]}...)")
        except Exception as e:
            print(f"\nError reading {args.file}: {e}")
    
    return 0


def main():
    """Main entry point."""
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(130))
    
    parser = _create_parser()
    args = parser.parse_args()
    
    # Route to appropriate command
    if args.cmd in ("encode", "enc", "e"):
        return cmd_encode(args)
    elif args.cmd in ("decode", "dec", "d"):
        return cmd_decode(args)
    elif args.cmd in ("info", "show", "status"):
        return cmd_info(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
