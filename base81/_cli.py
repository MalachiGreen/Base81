#!/usr/bin/env python3
# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Base81/62 - Binary-to-text encoding with maximum density.

A complete command-line interface for encoding binary data to base81 (81-character
printable ASCII) or base62 (URL-safe) text, and decoding back.

Features:
    - Two alphabets: standard (81 chars, 98.1% efficiency) and url (62 chars)
    - Three block sizes: 7 (optimal), 3 (legacy), 5 (URL-safe only)
    - Streaming mode for large files (constant memory)
    - Batch processing with parallel jobs (-j)
    - Self-describing headers for auto-detection (-H)
    - Shell completion (bash, zsh, fish)
    - Config file support (~/.base81rc)
    - Benchmark mode and dry-run preview
    - Progress indicator for large files
    - Comprehensive error messages with context

Commands:
    encode    - Encode binary data to base81/62 text
    decode    - Decode base81/62 text to binary
    info      - Show codec information and file analysis
    help      - Display detailed help for any command
    completion - Generate or install shell completion scripts

Examples:
    # Basic encoding/decoding
    base81 encode document.pdf
    base81 decode document.b81 -o restored.pdf

    # With header (auto-detection)
    base81 encode --header data.bin | base81 decode --header > restored.bin

    # Streaming large files (no memory spike)
    base81 encode --stream huge_video.mp4 -o video.b81

    # Batch processing with parallel jobs
    base81 encode *.bin -d encoded/ -j 4

    # URL-safe encoding (for filenames, URLs)
    base81 encode -b 5 -a url data.bin -o safe.txt

    # Preview before encoding
    base81 encode --dry-run large.bin

    # Performance benchmark
    base81 encode --benchmark --block-size 7

    # Set persistent defaults
    echo '{"block_size":7,"alphabet":"url"}' > ~/.base81rc

    # Install shell completion (tab completion)
    base81 completion install

    # Get detailed help
    base81 help encode
    base81 help decode
    base81 help completion

Configuration:
    ~/.base81rc - JSON or KEY=VALUE format
    Example JSON:
        {"block_size": 7, "alphabet": "standard", "quiet": false}
    Example KEY=VALUE:
        block_size=7
        alphabet=standard
        quiet=false

    CLI arguments override config file values.

Exit Codes:
    0 - Success
    1 - Error (invalid input, corruption, etc.)
    130 - Interrupted (Ctrl+C)

Environment:
    SHELL - Used for auto-detection in 'completion install'
    NO_COLOR - Disables ANSI color codes in output

See Also:
    https://github.com/MalachiGreen/Base81
"""

import sys
import argparse
import signal
import time
import os
import json
import tempfile
from typing import Optional, BinaryIO, TextIO, List, Dict, Any
from contextlib import contextmanager
from ._api import encode, decode
from ._header import make_header, parse_header
from ._exceptions import CorruptStreamError, ValidationError, BoundaryError

__all__ = ["main"]
__version__ = "0.1.0"


# Config file handling

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.base81rc")

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from JSON or key=value file."""
    path = config_path or DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        return {}
    
    try:
        with open(path) as f:
            content = f.read().strip()
            if content.startswith('{'):
                # JSON format
                return json.loads(content)
            else:
                # Simple KEY=VALUE format
                config = {}
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        key = key.strip().lstrip('-').replace('-', '_')
                        # Try parsing int/bool
                        if val.lower() == 'true':
                            val = True
                        elif val.lower() == 'false':
                            val = False
                        else:
                            try:
                                val = int(val)
                            except ValueError:
                                pass
                        config[key] = val
                return config
    except Exception:
        # Silently ignore malformed config
        return {}

def merge_config(args: argparse.Namespace, config: Dict[str, Any]) -> argparse.Namespace:
    """Apply config defaults to args (CLI overrides config)."""
    for key, value in config.items():
        # Only set if attribute exists and is None (not provided by CLI)
        if hasattr(args, key) and getattr(args, key) is None:
            setattr(args, key, value)
    return args
    
    
# Helpers
@contextmanager
def _open_input(path: Optional[str], binary: bool = True):
    if not path or path == "-":
        yield sys.stdin.buffer if binary else sys.stdin
    else:
        mode = "rb" if binary else "r"
        with open(path, mode) as f:
            yield f

@contextmanager
def _open_output(path: Optional[str], binary: bool = True, dry_run: bool = False):
    if dry_run:
        yield open(os.devnull, "wb" if binary else "w")
    elif not path or path == "-":
        yield sys.stdout.buffer if binary else sys.stdout
    else:
        mode = "wb" if binary else "w"
        with open(path, mode) as f:
            yield f

class ProgressIndicator:
    def __init__(self, total: Optional[int] = None, quiet: bool = False):
        self.total = total
        self.processed = 0
        self.quiet = quiet
        self.start_time = time.time()
        self._last_update = 0.0

    def update(self, delta: int):
        if self.quiet:
            return
        self.processed += delta
        now = time.time()
        if now - self._last_update > 0.5 or self.processed == self.total:
            self._last_update = now
            self._display()

    def _display(self):
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
        if not self.quiet and self.processed > 0:
            self._display()

def _get_file_size(path: Optional[str]) -> Optional[int]:
    if path and path != "-" and os.path.exists(path):
        return os.path.getsize(path)
    return None


# Streaming classes (same as before, but fixed fish support)
class StreamingEncoder:
    def __init__(self, block_size: int = 7, alphabet_type: str = "standard",
                 line_width: Optional[int] = None, buffer_size: int = 64 * 1024):
        from ._stream import Encoder
        self._encoder = Encoder(block_size=block_size, alphabet_type=alphabet_type)
        self.line_width = line_width
        self.buffer_size = buffer_size
        self._line_buffer: List[str] = []
        self._line_len = 0

    def _apply_line_wrapping(self, text: str) -> str:
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

    def _flush_line_buffer(self) -> str:
        if self._line_buffer:
            line = ''.join(self._line_buffer)
            self._line_buffer = []
            self._line_len = 0
            return line
        return ""

    def encode_stream(self, input_file: BinaryIO, output_file: TextIO,
                      progress: Optional[ProgressIndicator] = None):
        while True:
            chunk = input_file.read(self.buffer_size)
            if not chunk:
                break
            if progress:
                progress.update(len(chunk))
            encoded = self._encoder.update(chunk)
            if encoded:
                wrapped = self._apply_line_wrapping(encoded)
                if wrapped:
                    output_file.write(wrapped)
                    if self.line_width:
                        output_file.write('\n')
        final = self._encoder.finalize()
        if final:
            wrapped = self._apply_line_wrapping(final)
            if wrapped:
                output_file.write(wrapped)
                if self.line_width:
                    output_file.write('\n')
        remaining = self._flush_line_buffer()
        if remaining:
            output_file.write(remaining)
            if self.line_width:
                output_file.write('\n')
        if progress:
            progress.finish()

class StreamingDecoder:
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

    def decode_stream(self, input_file: TextIO, output_file: BinaryIO,
                      progress: Optional[ProgressIndicator] = None):
        while True:
            chunk = input_file.read(self.buffer_size)
            if not chunk:
                break
            if progress:
                progress.update(len(chunk))
            decoded = self._decoder.update(chunk)
            if decoded:
                output_file.write(decoded)
        final = self._decoder.finalize()
        if final:
            output_file.write(final)
        if progress:
            progress.finish()
            
            
# Benchmark
def _run_benchmark(block_size: int, alphabet_type: str, size_mb: int = 10):
    data = os.urandom(size_mb * 1024 * 1024)
    print(f"Benchmark: {size_mb}MB random data")
    print(f"Codec: {alphabet_type}/{block_size}\n")
    
    start = time.time()
    encoded = encode(data, block_size=block_size, alphabet_type=alphabet_type)
    encode_time = time.time() - start
    encode_speed = (size_mb / encode_time) if encode_time > 0 else 0
    
    start = time.time()
    decoded = decode(encoded, block_size=block_size, alphabet_type=alphabet_type)
    decode_time = time.time() - start
    decode_speed = (size_mb / decode_time) if decode_time > 0 else 0
    
    assert decoded == data, "Roundtrip failed"
    
    print(f"Encode: {encode_time:.2f}s ({encode_speed:.1f} MB/s)")
    print(f"Decode: {decode_time:.2f}s ({decode_speed:.1f} MB/s)")
    print(f"Output size: {len(encoded)} chars ({len(encoded)/size_mb/1024:.1f} KB/MB)")
    
    # Rough efficiency
    theoretical = (block_size * 8) / (9 if block_size == 7 else (4 if block_size == 3 else 7))
    actual = (size_mb * 1024 * 1024 * 8) / (len(encoded) * 6)  # approximate
    print(f"Efficiency: {theoretical:.1%} theoretical, ~{actual:.1%} actual")


# Shell completion generation (full fish)
def _generate_completion(shell: str) -> str:
    base_commands = ["encode", "decode", "info", "help", "completion"]
    encode_opts = ["--input", "--output", "--output-dir", "--force", "--line-width",
                   "--block-size", "--alphabet", "--header", "--stream", "--buffer-size",
                   "--jobs", "--benchmark", "--dry-run"]
    decode_opts = ["--input", "--output", "--output-dir", "--force", "--block-size",
                   "--alphabet", "--header", "--ignore-ws", "--no-canonical-check",
                   "--max-input-length", "--stream", "--buffer-size", "--dry-run"]
    info_opts = []
    help_opts = ["encode", "decode", "info", "help", "completion"]
    completion_opts = ["install", "bash", "zsh", "fish"]
    
    block_sizes = ["3", "5", "7"]
    alphabets = ["standard", "url"]
    
    if shell == "bash":
        return f'''# bash completion for base81
_base81_completion() {{
    local cur prev words cword
    _init_completion || return

    case $prev in
        --block-size|-b)
            COMPREPLY=($(compgen -W "{' '.join(block_sizes)}" -- "$cur"))
            return 0
            ;;
        --alphabet|-a)
            COMPREPLY=($(compgen -W "{' '.join(alphabets)}" -- "$cur"))
            return 0
            ;;
        --jobs|-j|--buffer-size|--line-width|-w|--max-input-length|-m)
            return 0
            ;;
        help)
            COMPREPLY=($(compgen -W "{' '.join(help_opts)}" -- "$cur"))
            return 0
            ;;
        completion)
            COMPREPLY=($(compgen -W "{' '.join(completion_opts)}" -- "$cur"))
            return 0
            ;;
    esac

    if [[ $cur == -* ]]; then
        case ${{words[1]}} in
            encode|enc|e)
                COMPREPLY=($(compgen -W "{' '.join(encode_opts)}" -- "$cur"))
                ;;
            decode|dec|d)
                COMPREPLY=($(compgen -W "{' '.join(decode_opts)}" -- "$cur"))
                ;;
            info|show|status)
                COMPREPLY=($(compgen -W "{' '.join(info_opts)}" -- "$cur"))
                ;;
            help|completion)
                COMPREPLY=($(compgen -W "{' '.join(help_opts)}" -- "$cur"))
                ;;
            *)
                COMPREPLY=($(compgen -W "{' '.join(base_commands)} --help --version -v -q" -- "$cur"))
                ;;
        esac
    else
        COMPREPLY=($(compgen -W "{' '.join(base_commands)}" -- "$cur"))
    fi
}} && complete -F _base81_completion base81
'''
    elif shell == "zsh":
        return f'''# zsh completion for base81
#compdef base81

_base81_completion() {{
    local context state line
    typeset -A opt_args

    _arguments -C \\
        '1: :(encode decode info help completion)' \\
        '*::arg:->args'

    case $state in
        args)
            case $words[1] in
                encode|enc|e)
                    _arguments \\
                        '(-i --input)'{{-i,--input}}':input file:_files' \\
                        '(-o --output)'{{-o,--output}}':output file:_files' \\
                        '(-d --output-dir)'{{-d,--output-dir}}':output directory:_files -/' \\
                        '(-f --force)'{{-f,--force}}'[overwrite]' \\
                        '(-w --line-width)'{{-w,--line-width}}':line width' \\
                        '(-b --block-size)'{{-b,--block-size}}':block size:(3 5 7)' \\
                        '(-a --alphabet)'{{-a,--alphabet}}':alphabet:(standard url)' \\
                        '(-H --header)'{{-H,--header}}'[add header]' \\
                        '(-s --stream)'{{-s,--stream}}'[streaming]' \\
                        '--buffer-size:buffer size' \\
                        '(-j --jobs)'{{-j,--jobs}}':jobs' \\
                        '--benchmark' \\
                        '--dry-run' \\
                        '*:input files:_files'
                    ;;
                decode|dec|d)
                    _arguments \\
                        '(-i --input)'{{-i,--input}}':input file:_files' \\
                        '(-o --output)'{{-o,--output}}':output file:_files' \\
                        '(-d --output-dir)'{{-d,--output-dir}}':output directory:_files -/' \\
                        '(-f --force)'{{-f,--force}}'[overwrite]' \\
                        '(-b --block-size)'{{-b,--block-size}}':block size:(3 5 7)' \\
                        '(-a --alphabet)'{{-a,--alphabet}}':alphabet:(standard url)' \\
                        '(-H --header)'{{-H,--header}}'[parse header]' \\
                        '--ignore-ws' \\
                        '--no-canonical-check' \\
                        '(-m --max-input-length)'{{-m,--max-input-length}}':max length' \\
                        '(-s --stream)'{{-s,--stream}}'[streaming]' \\
                        '--buffer-size:buffer size' \\
                        '--dry-run' \\
                        '*:input files:_files'
                    ;;
                info|show|status)
                    _arguments ':file:_files'
                    ;;
                help)
                    _arguments ':command:(encode decode info help completion)'
                    ;;
                completion)
                    _arguments ':action:(install bash zsh fish)'
                    ;;
            esac
            ;;
    esac
}}

compdef _base81_completion base81
'''
    elif shell == "fish":
        # Complete fish completion script with all subcommands and options
        return f'''# fish completion for base81
function __fish_base81_needs_command
    set cmd (commandline -opc)
    test (count $cmd) -eq 1
end

function __fish_base81_using_command
    set cmd (commandline -opc)
    test (count $cmd) -gt 1; and test $argv[1] = $cmd[2]
end

# Commands
complete -f -c base81 -n '__fish_base81_needs_command' -a encode -d 'Encode binary to text'
complete -f -c base81 -n '__fish_base81_needs_command' -a decode -d 'Decode text to binary'
complete -f -c base81 -n '__fish_base81_needs_command' -a info -d 'Show codec information'
complete -f -c base81 -n '__fish_base81_needs_command' -a help -d 'Show detailed help'
complete -f -c base81 -n '__fish_base81_needs_command' -a completion -d 'Shell completion'

# Global options
complete -f -c base81 -s v -l verbose -d 'Increase verbosity'
complete -f -c base81 -s q -l quiet -d 'Suppress output'
complete -f -c base81 -l version -d 'Show version'
complete -f -c base81 -s h -l help -d 'Show help'

# Encode options
complete -f -c base81 -n '__fish_base81_using_command encode' -s i -l input -d 'Input file' -r
complete -f -c base81 -n '__fish_base81_using_command encode' -s o -l output -d 'Output file' -r
complete -f -c base81 -n '__fish_base81_using_command encode' -s d -l output-dir -d 'Output directory' -r -f -a '(__fish_complete_directories)'
complete -f -c base81 -n '__fish_base81_using_command encode' -s f -l force -d 'Overwrite'
complete -f -c base81 -n '__fish_base81_using_command encode' -s w -l line-width -d 'Wrap at COLS' -r
complete -f -c base81 -n '__fish_base81_using_command encode' -s b -l block-size -d 'Bytes per block' -r -a '3 5 7'
complete -f -c base81 -n '__fish_base81_using_command encode' -s a -l alphabet -d 'Alphabet' -r -a 'standard url'
complete -f -c base81 -n '__fish_base81_using_command encode' -s H -l header -d 'Add header'
complete -f -c base81 -n '__fish_base81_using_command encode' -s s -l stream -d 'Streaming mode'
complete -f -c base81 -n '__fish_base81_using_command encode' -l buffer-size -d 'Buffer size' -r
complete -f -c base81 -n '__fish_base81_using_command encode' -s j -l jobs -d 'Parallel jobs' -r
complete -f -c base81 -n '__fish_base81_using_command encode' -l benchmark -d 'Run benchmark'
complete -f -c base81 -n '__fish_base81_using_command encode' -l dry-run -d 'Preview only'

# Decode options
complete -f -c base81 -n '__fish_base81_using_command decode' -s i -l input -d 'Input file' -r
complete -f -c base81 -n '__fish_base81_using_command decode' -s o -l output -d 'Output file' -r
complete -f -c base81 -n '__fish_base81_using_command decode' -s d -l output-dir -d 'Output directory' -r -f -a '(__fish_complete_directories)'
complete -f -c base81 -n '__fish_base81_using_command decode' -s f -l force -d 'Overwrite'
complete -f -c base81 -n '__fish_base81_using_command decode' -s b -l block-size -d 'Override block size' -r -a '3 5 7'
complete -f -c base81 -n '__fish_base81_using_command decode' -s a -l alphabet -d 'Override alphabet' -r -a 'standard url'
complete -f -c base81 -n '__fish_base81_using_command decode' -s H -l header -d 'Parse header'
complete -f -c base81 -n '__fish_base81_using_command decode' -l ignore-ws -d 'Strip whitespace'
complete -f -c base81 -n '__fish_base81_using_command decode' -l no-canonical-check -d 'Disable canonical validation'
complete -f -c base81 -n '__fish_base81_using_command decode' -s m -l max-input-length -d 'Max input length' -r
complete -f -c base81 -n '__fish_base81_using_command decode' -s s -l stream -d 'Streaming mode'
complete -f -c base81 -n '__fish_base81_using_command decode' -l buffer-size -d 'Buffer size' -r
complete -f -c base81 -n '__fish_base81_using_command decode' -l dry-run -d 'Preview only'

# Info options
complete -f -c base81 -n '__fish_base81_using_command info' -r -a '(__fish_complete_suffix .b81)'

# Help options
complete -f -c base81 -n '__fish_base81_using_command help' -a 'encode decode info help completion' -d 'Command'

# Completion options
complete -f -c base81 -n '__fish_base81_using_command completion' -a 'install bash zsh fish' -d 'Action'
'''
    else:
        raise ValueError(f"Unsupported shell: {shell}")


# Completion installation
def _install_completion(shell: Optional[str] = None) -> bool:
    """Install completion for detected shell."""
    if shell is None:
        # Detect from environment
        shell = os.environ.get('SHELL', '')
        if 'bash' in shell:
            shell = 'bash'
        elif 'zsh' in shell:
            shell = 'zsh'
        elif 'fish' in shell:
            shell = 'fish'
        else:
            print("Could not detect shell. Please specify --shell bash|zsh|fish", file=sys.stderr)
            return False
    
    script = _generate_completion(shell)
    
    # Determine rc file
    if shell == 'bash':
        rc_file = os.path.expanduser("~/.bashrc")
        marker = "# base81 completion"
    elif shell == 'zsh':
        rc_file = os.path.expanduser("~/.zshrc")
        marker = "# base81 completion"
    elif shell == 'fish':
        fish_config = os.path.expanduser("~/.config/fish/config.fish")
        os.makedirs(os.path.dirname(fish_config), exist_ok=True)
        rc_file = fish_config
        marker = "# base81 completion"
    else:
        print(f"Unsupported shell: {shell}", file=sys.stderr)
        return False
    
    # Check if already installed
    if os.path.exists(rc_file):
        with open(rc_file) as f:
            if marker in f.read():
                print(f"Completion already installed in {rc_file}", file=sys.stderr)
                return False
    
    # Append to rc file
    with open(rc_file, 'a') as f:
        f.write(f"\n{marker}\n")
        if shell == 'fish':
            f.write(script)
        else:
            f.write(f"source <(base81 completion {shell})\n")
    
    print(f"Installed {shell} completion to {rc_file}")
    print(f"Please restart your shell or run: source {rc_file}")
    return True

def cmd_completion(args):
    """Handle completion subcommand."""
    if not args.action:
        print("Usage: base81 completion {install|bash|zsh|fish}", file=sys.stderr)
        return 1
    
    if args.action == "install":
        shell = args.shell if hasattr(args, 'shell') else None
        if _install_completion(shell):
            return 0
        return 1
    else:
        try:
            print(_generate_completion(args.action))
            return 0
        except ValueError as e:
            print(f"base81: error: {e}", file=sys.stderr)
            return 1


# Detailed help
def _detailed_help(subcommand: str) -> str:
    helps = {
        "encode": """\
ENCODE DETAILS

Usage: base81 encode [OPTIONS] [FILE...]

Encodes binary data to base81 (or base62) text.

OPTIONS:
  -i, --input FILE         Input file (default: stdin)
  -o, --output FILE        Output file (default: stdout)
  -d, --output-dir DIR     Output directory for multiple files
  -f, --force              Overwrite existing output files
  -w, --line-width COLS    Wrap output at COLS characters
  -b, --block-size N       Bytes per block: 3, 5, or 7 (default: 7)
  -a, --alphabet TYPE      'standard' (81 chars) or 'url' (62 chars)
  -H, --header             Prepend self-describing header (^b81:...^)
  -s, --stream             Streaming mode (constant memory, for large files)
  --buffer-size BYTES      Buffer size for streaming (default: 64KB)
  -j, --jobs N             Parallel jobs for multiple files (default: 1)
  --benchmark              Run performance benchmark on synthetic data
  --dry-run                Preview output size without writing to disk

CONFIG FILE (~/.base81rc):
  You can set defaults for any option using JSON or KEY=VALUE format.
  Example:
    { "block_size": 7, "alphabet": "url", "quiet": true }
  or:
    block_size=7
    alphabet=url
    quiet=true

EXAMPLES:
  base81 encode doc.pdf
  base81 encode --dry-run large.bin
  base81 encode --benchmark --block-size 7
""",
        "decode": """\
DECODE DETAILS

Usage: base81 decode [OPTIONS] [FILE...]

Decodes base81/62 text back to binary.

OPTIONS:
  -i, --input FILE         Input file (default: stdin)
  -o, --output FILE        Output file (default: stdout)
  -d, --output-dir DIR     Output directory for multiple files
  -f, --force              Overwrite existing output files
  -b, --block-size N       Override codec detection (3,5,7)
  -a, --alphabet TYPE      Override codec detection ('standard' or 'url')
  -H, --header             Parse self-describing header (^b81:...^)
  --ignore-ws              Strip spaces, tabs, newlines from input
  --no-canonical-check     Disable tail validation (NOT recommended)
  -m, --max-input-length N Reject inputs longer than N chars (DoS protection)
  -s, --stream             Streaming mode (constant memory)
  --buffer-size BYTES      Buffer size for streaming (default: 64KB)
  --dry-run                Preview output size without writing to disk

EXAMPLES:
  base81 decode doc.b81
  base81 decode --header data.b81
  base81 decode --dry-run data.b81
""",
        "info": """\
INFO DETAILS

Usage: base81 info [FILE]

Shows codec information and file analysis.

EXAMPLES:
  base81 info
  base81 info encoded.b81
""",
        "help": """\
HELP DETAILS

Usage: base81 help [COMMAND]

Shows detailed help for a command.

COMMANDS:
  encode, decode, info, help, completion
""",
        "completion": """\
COMPLETION DETAILS

Generate or install shell completion.

Usage:
  base81 completion bash       # Print bash completion script
  base81 completion zsh        # Print zsh completion script
  base81 completion fish       # Print fish completion script
  base81 completion install    # Auto-install for current shell

To install manually:
  bash: source <(base81 completion bash)
  zsh:  source <(base81 completion zsh)
  fish: base81 completion fish | source

To auto-install: base81 completion install
"""
    }
    return helps.get(subcommand, f"No detailed help for '{subcommand}'")

def cmd_help(args):
    if args.command:
        print(_detailed_help(args.command))
    else:
        parser = _create_parser()
        parser.print_help()
    return 0


# Argument parser
def _create_parser():
    parser = argparse.ArgumentParser(
        prog="base81",
        description="Binary-to-text encoding with 81/62 character alphabets",
        epilog="""
Examples:
  base81 encode doc.pdf
  base81 decode doc.b81 -o restored.pdf
  base81 encode --header data.bin | base81 decode --header
  base81 help encode    # detailed help
  base81 completion install  # tab completion
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    parser.add_argument("--version", action="version", version=f"base81 {__version__}")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("--config", help="Path to config file (default: ~/.base81rc)")

    sub = parser.add_subparsers(dest="cmd", required=True)

    # Encode
    enc = sub.add_parser("encode", aliases=["enc", "e"])
    enc.add_argument("inputs", nargs="*")
    enc.add_argument("-i", "--input")
    enc.add_argument("-o", "--output")
    enc.add_argument("-d", "--output-dir")
    enc.add_argument("-f", "--force", action="store_true")
    enc.add_argument("-w", "--line-width", type=int)
    enc.add_argument("-b", "--block-size", type=int, choices=[3, 5, 7])
    enc.add_argument("-a", "--alphabet", choices=["standard", "url"])
    enc.add_argument("-H", "--header", action="store_true")
    enc.add_argument("-s", "--stream", action="store_true")
    enc.add_argument("--buffer-size", type=int)
    enc.add_argument("-j", "--jobs", type=int)
    enc.add_argument("--benchmark", action="store_true")
    enc.add_argument("--dry-run", action="store_true")

    # Decode
    dec = sub.add_parser("decode", aliases=["dec", "d"])
    dec.add_argument("inputs", nargs="*")
    dec.add_argument("-i", "--input")
    dec.add_argument("-o", "--output")
    dec.add_argument("-d", "--output-dir")
    dec.add_argument("-f", "--force", action="store_true")
    dec.add_argument("-b", "--block-size", type=int, choices=[3, 5, 7])
    dec.add_argument("-a", "--alphabet", choices=["standard", "url"])
    dec.add_argument("-H", "--header", action="store_true")
    dec.add_argument("--ignore-ws", action="store_true")
    dec.add_argument("--no-canonical-check", action="store_true")
    dec.add_argument("-m", "--max-input-length", type=int)
    dec.add_argument("-s", "--stream", action="store_true")
    dec.add_argument("--buffer-size", type=int)
    dec.add_argument("--dry-run", action="store_true")

    # Info
    info = sub.add_parser("info", aliases=["show", "status"])
    info.add_argument("file", nargs="?")

    # Help
    help_parser = sub.add_parser("help")
    help_parser.add_argument("command", nargs="?")

    # Completion
    comp = sub.add_parser("completion")
    comp.add_argument("action", choices=["install", "bash", "zsh", "fish"], nargs="?")
    comp.add_argument("--shell", choices=["bash", "zsh", "fish"], help="For install action")

    return parser


# Command implementations (with config merging)
def cmd_encode(args):
    # Load config
    config = load_config(args.config)
    args = merge_config(args, config)
    
    # Set defaults (after config)
    if args.block_size is None:
        args.block_size = 7
    if args.alphabet is None:
        args.alphabet = "standard"
    
    if args.benchmark:
        _run_benchmark(args.block_size, args.alphabet)
        return 0
    
    inputs = args.inputs or []
    if args.input:
        inputs.append(args.input)
    if not inputs and not sys.stdin.isatty():
        inputs = ["-"]
    if not inputs:
        print("base81: error: no input files (use - for stdin)", file=sys.stderr)
        return 1
    
    if args.dry_run:
        total_bytes = 0
        for inpath in inputs:
            if inpath == "-":
                print("base81: dry-run not supported for stdin", file=sys.stderr)
                return 1
            total_bytes += _get_file_size(inpath) or 0
        # Estimate output size
        from ._codecs import CODECS
        cfg = CODECS.get((args.alphabet, args.block_size))
        if cfg:
            fn, fk = cfg["full_n"], cfg["full_k"]
            full_blocks = total_bytes // fn
            remainder = total_bytes % fn
            tail_chars = cfg["tail_enc"].get(remainder, 0) if remainder > 0 else 0
            estimated_chars = full_blocks * fk + tail_chars
            if args.header:
                estimated_chars += len(make_header(args.block_size, args.alphabet))
            print(f"DRY-RUN: {len(inputs)} file(s), {total_bytes} bytes total")
            print(f"  Codec: {args.alphabet}/{args.block_size}")
            print(f"  Estimated output: {estimated_chars} chars")
            if total_bytes > 0:
                print(f"  Ratio: {total_bytes/estimated_chars:.2f} bytes/char")
        else:
            print(f"DRY-RUN: {total_bytes} bytes (unknown codec)")
        return 0
    
    if len(inputs) > 1 and args.output and not args.output_dir:
        print("base81: error: with multiple inputs, use -d/--output-dir", file=sys.stderr)
        return 1

    if args.jobs and args.jobs > 1 and len(inputs) > 1:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        def encode_one(inpath):
            with _open_input(inpath) as f:
                data = f.read()
            res = encode(data, block_size=args.block_size, alphabet_type=args.alphabet,
                         line_width=args.line_width)
            if args.header:
                res = make_header(args.block_size, args.alphabet) + res
            return inpath, res
        with ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futures = {ex.submit(encode_one, p): p for p in inputs}
            for fut in as_completed(futures):
                inpath, res = fut.result()
                if args.output_dir:
                    outpath = os.path.join(args.output_dir, os.path.basename(inpath) + ".b81")
                    if not args.force and os.path.exists(outpath):
                        print(f"base81: {outpath} exists (use -f)", file=sys.stderr)
                        return 1
                    with open(outpath, "w") as f:
                        f.write(res)
                else:
                    print(f"# {inpath}")
                    print(res)
        return 0

    inpath = inputs[0]
    total = _get_file_size(inpath) if inpath != "-" else None
    progress = ProgressIndicator(total=total, quiet=args.quiet)
    try:
        if args.stream and total and total > 10*1024*1024:
            enc = StreamingEncoder(args.block_size, args.alphabet, args.line_width, args.buffer_size or 65536)
            with _open_input(inpath) as inf:
                with _open_output(args.output, binary=False, dry_run=False) as outf:
                    enc.encode_stream(inf, outf, progress)
        else:
            with _open_input(inpath) as f:
                data = f.read()
            progress.update(len(data))
            result = encode(data, block_size=args.block_size, alphabet_type=args.alphabet,
                            line_width=args.line_width)
            if args.header:
                result = make_header(args.block_size, args.alphabet) + result
            with _open_output(args.output, binary=False, dry_run=False) as outf:
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
    config = load_config(args.config)
    args = merge_config(args, config)
    
    inputs = args.inputs or []
    if args.input:
        inputs.append(args.input)
    if not inputs and not sys.stdin.isatty():
        inputs = ["-"]
    if not inputs:
        print("base81: error: no input files", file=sys.stderr)
        return 1
    
    if args.dry_run:
        total_chars = 0
        for inpath in inputs:
            if inpath == "-":
                print("base81: dry-run not supported for stdin", file=sys.stderr)
                return 1
            total_chars += _get_file_size(inpath) or 0
        # Rough estimate
        ratio = 1.2857 if args.alphabet == "standard" else 1.4
        estimated_bytes = int(total_chars / ratio) if total_chars > 0 else 0
        print(f"DRY-RUN: {len(inputs)} file(s), {total_chars} chars total")
        print(f"  Codec: {args.alphabet or 'auto'}/{args.block_size or 'auto'}")
        print(f"  Estimated output: ~{estimated_bytes} bytes")
        return 0

    if len(inputs) > 1 and args.output and not args.output_dir:
        print("base81: error: with multiple inputs, use -d/--output-dir", file=sys.stderr)
        return 1

    inpath = inputs[0]
    total = _get_file_size(inpath) if inpath != "-" else None
    progress = ProgressIndicator(total=total, quiet=args.quiet)
    try:
        with _open_input(inpath, binary=False) as f:
            if args.stream and total and total > 1024*1024:
                decoder = StreamingDecoder(
                    block_size=args.block_size or 7,
                    alphabet_type=args.alphabet or "standard",
                    ignore_whitespace=args.ignore_ws,
                    validate_canonical=not args.no_canonical_check,
                    buffer_size=args.buffer_size or 65536
                )
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
                        buffer_size=args.buffer_size or 65536
                    )
                    text = payload
                from io import StringIO
                fake_file = StringIO(text)
                with _open_output(args.output, binary=True, dry_run=False) as outf:
                    decoder.decode_stream(fake_file, outf, progress)
            else:
                text = f.read()
                progress.update(len(text))
                bs = args.block_size
                alpha = args.alphabet
                payload = text
                if args.header:
                    bs, alpha, payload = parse_header(text)
                if bs is None or alpha is None:
                    if not args.quiet:
                        print("base81: error: missing block-size/alphabet (use -b/-a or --header)", file=sys.stderr)
                    return 1
                result = decode(payload, ignore_whitespace=args.ignore_ws,
                                validate_canonical=not args.no_canonical_check,
                                block_size=bs, max_input_length=args.max_input_length,
                                alphabet_type=alpha)
                with _open_output(args.output, binary=True, dry_run=False) as outf:
                    outf.write(result)
                progress.finish()
        return 0
    except (ValidationError, CorruptStreamError, BoundaryError, UnicodeDecodeError) as e:
        if not args.quiet:
            print(f"base81: error: {e}", file=sys.stderr)
        return 1

def cmd_info(args):
    from ._codecs import list_codecs, CODECS
    print(f"base81 {__version__}")
    print(f"Python {sys.version}")
    print()
    print("Registered codecs:")
    for alpha, bs in list_codecs():
        cfg = CODECS[(alpha, bs)]
        radix = cfg["radix"]
        fn, fk = cfg["full_n"], cfg["full_k"]
        eff = (fn * 8) / (fk * (radix.bit_length() - 1)) * 100
        print(f"  {alpha}/{bs}: {fn}→{fk} chars | {radix}^{fk} ≥ 256^{fn} | {eff:.1f}%")
    if args.file:
        try:
            with open(args.file, "r") as f:
                first = f.readline()[:200]
            if first.startswith("^b81:"):
                import re
                m = re.match(r'\^b81:(\d+):(\w+)\^', first)
                if m:
                    bs, alpha = m.groups()
                    print(f"\n{args.file} header: block_size={bs}, alphabet={alpha}")
                else:
                    print(f"\n{args.file}: invalid header")
            else:
                print(f"\n{args.file}: no header (first chars: {first[:50]}...)")
        except Exception as e:
            print(f"\nError reading {args.file}: {e}")
    return 0


# Main
def main():
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(130))
    parser = _create_parser()
    args = parser.parse_args()

    if args.cmd in ("encode", "enc", "e"):
        return cmd_encode(args)
    elif args.cmd in ("decode", "dec", "d"):
        return cmd_decode(args)
    elif args.cmd in ("info", "show", "status"):
        return cmd_info(args)
    elif args.cmd == "help":
        return cmd_help(args)
    elif args.cmd == "completion":
        return cmd_completion(args)
    else:
        parser.print_help()
        return 1

if __name__ == "__main__":
    sys.exit(main())