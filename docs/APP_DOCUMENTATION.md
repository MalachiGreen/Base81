# Base81/62 Documentation

**Multi‑Radix Binary‑to‑Text Codec**  
Version `0.1.0`

****

## Overview

Base81/62 encodes binary data to printable ASCII strings using either an 81‑character alphabet (full ASCII printable set excluding `^` and `~`) or a 62‑character URL‑safe alphabet. Achieves ~23% better density than base64 (81 vs 64 characters) while maintaining safe transport properties.

**Key Features:**
- Two alphabets: `standard` (81 chars, high density) and `url` (62 chars, safe for URLs/domain names)
- Multiple block sizes: 3, 5, or 7 bytes per group
- Streaming API with memory protection
- Self‑describing header format
- Canonical encoding (no ambiguous padding)
- CLI tool with batch processing, parallel jobs, streaming, config files, shell completion

****

## Installation

```bash
# Core library (no optional dependencies)
pip install git+https://github.com/MalachiGreen/Base81.git

# With CLI tab‑completion (requires argcomplete)
pip install "base81[cli] @ git+https://github.com/MalachiGreen/Base81.git"
```

After installation, the `base81` command is available.

****

## Alphabets

### Standard Alphabet (81 characters)

```text
0123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz!#$%&()*+-./:;=?@_{}[]
```

- Excludes `I`, `O`, `l` (visually ambiguous)  
- Excludes `^` (reserved for header delimiter)  
- Excludes `~` (removed due to alphabet completion and overall redundancy)  
- Includes 22 special characters

### URL Alphabet (62 characters)

```text
0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
```

- Full alphanumeric sets  
- No special characters (safe for URLs, DNS labels, JSON)

****

## Codec Configurations

| Alphabet | Block Size | Bytes → Chars | Full Capacity | Tail Handling |
|----------|------------|---------------|---------------|---------------|
| standard | 3 | 3 → 4 | 81⁴ ≥ 256³ | Fixed: {1→2, 2→3} |
| standard | 7 | 7 → 9 | 81⁹ ≥ 256⁷ | Dynamic: 1‑6 bytes → 2‑8 chars |
| url | 5 | 5 → 7 | 62⁷ ≥ 256⁵ | Dynamic: 1‑4 bytes → 2‑6 chars |

### Why block sizes 3, 5, 7?

- **3 bytes (standard):** Simple fixed mapping, minimal overhead for small data  
- **7 bytes (standard):** Optimal packing for 81‑character alphabet  
- **5 bytes (url):** Best density for 62‑character alphabet without overflow

****

## API Reference

### Core Functions

#### `encode(data, *, line_width=None, block_size=7, alphabet_type="standard")`

Encode bytes to base‑N string.

**Parameters:**

- `data` (`bytes`/`bytearray`): Input binary data  
- `line_width` (`int`, optional): Wrap output every N characters  
- `block_size` (`int`): 3, 5, or 7 (must match alphabet)  
- `alphabet_type` (`str`): `"standard"` or `"url"`

**Returns:** `str`

**Raises:**

- `TypeError`: Non‑bytes input  
- `ValidationError`: Unknown codec or invalid `line_width`  
- `BoundaryError`: Input exceeds limits (if using streaming wrapper)

**Example:**

```python
from base81 import encode

data = b"Hello World"
encoded = encode(data, block_size=7, alphabet_type="standard")
print(encoded)  # A]$gf-jnt0jbQcA
```

---

#### `decode(s, *, ignore_whitespace=False, validate_canonical=True, block_size=7, max_input_length=None, alphabet_type="standard")`

Decode base‑N string to bytes.

**Parameters:**

- `s` (`str`): Encoded string  
- `ignore_whitespace` (`bool`): Strip spaces/tabs/newlines  
- `validate_canonical` (`bool`): Reject non‑canonical tails  
- `block_size` (`int`): Must match encoding codec  
- `max_input_length` (`int`, optional): Reject strings longer than N chars  
- `alphabet_type` (`str`): `"standard"` or `"url"`

**Returns:** `bytes`

**Raises:**

- `TypeError`: Non‑string input  
- `ValidationError`: Invalid character, whitespace (if not ignored), non‑canonical tail  
- `CorruptStreamError`: Malformed block, overflow, bad tail length  
- `BoundaryError`: Input exceeds `max_input_length`

**Example:**

```python
from base81 import decode

encoded = "A]$gf-jnt0jbQcA"
decoded = decode(encoded, block_size=7, alphabet_type="standard")
print(decoded)  # b"Hello World"
```

---

### Streaming API

#### `class Encoder(block_size=7, alphabet_type="standard", max_input_length=None, max_buffer=1048576)`

**Methods:**

- `update(data: bytes) -> str`: Process bytes, return encoded chars (may be empty)  
- `finalize() -> str`: Flush remaining bytes, return final chars  
- `diagnostics() -> dict`: Returns `{"buffer_len": int, "total_bytes": int}`

**Buffer Limits:**

- `max_input_length`: Total bytes across all `update()` calls  
- `max_buffer`: Maximum pending bytes before forced encoding  
- `BoundaryError` raised if exceeded (state preserved for recovery)

**Example:**

```python
from base81 import Encoder

enc = Encoder(block_size=7, max_buffer=1024*1024)
chunk1 = enc.update(b"large data " * 1000)
chunk2 = enc.update(b"more data " * 1000)
final = enc.finalize()
print(chunk1 + chunk2 + final)
```

---

#### `class Decoder(ignore_whitespace=False, validate_canonical=True, block_size=7, max_input_length=None, max_buffer=1048576, alphabet_type="standard")`

**Methods:**

- `update(s: str) -> bytes`: Process chars, return decoded bytes (may be empty)  
- `finalize() -> bytes`: Flush remaining chars, validate tail, return final bytes  
- `diagnostics() -> dict`: Returns `{"buffer_len": int, "total_chars": int, "chunks": int}`

**Buffer Limits:**

- `max_input_length`: Total chars across all `update()` calls  
- `max_buffer`: Maximum pending chars (must be ≥ `full_k + max_tail`)  
- `BoundaryError` raised if exceeded

**Example:**

```python
from base81 import Decoder

dec = Decoder(block_size=7, alphabet_type="standard")
data = bytearray()
data.extend(dec.update("ABC..."))
data.extend(dec.update("DEF..."))
data.extend(dec.finalize())
```

---

### Header Support

Self‑describing format: `^b81:{block_size}:{alphabet_type}^{payload}`

#### `make_header(block_size, alphabet_type) -> str`

Create header for given codec.

#### `parse_header(s: str) -> tuple[int, str, str]`

Extract `(block_size, alphabet_type, payload)` from header‑prefixed string.

**Example:**

```python
from base81 import make_header, parse_header

header = make_header(7, "standard")
full = header + encode(b"data")
bs, alpha, payload = parse_header(full)
```

---

### Utilities

#### `get_codec(alphabet_type, block_size) -> dict | None`

Return codec configuration or `None` if not registered.

Config dict keys:

- `radix`: Alphabet size (81 or 62)  
- `full_n`: Bytes per full block (3,5,7)  
- `full_k`: Chars per full block (4,7,9)  
- `tail_enc`: `{remainder_bytes: output_chars}`  
- `tail_dec`: `{input_chars: decoded_bytes}`  
- `max_tail`: Maximum tail chars

#### `list_codecs() -> list[tuple[str, int]]`

Return all registered `(alphabet_type, block_size)` pairs.

---

### Exception Hierarchy

| Exception | When Raised |
|-----------|-------------|
| `CodecError` | Root exception (base class) |
| `ValidationError` | Invalid alphabet character, missing header, non‑canonical tail, bad parameter |
| `CorruptStreamError` | Block overflow, wrong tail length, length mismatch |
| `BoundaryError` | `max_input_length` or `max_buffer` exceeded |

**Example:**

```python
from base81 import decode, CorruptStreamError

try:
    result = decode(malformed_string)
except CorruptStreamError as e:
    print(f"Stream corrupted: {e}")
```

****

## CLI Usage

After installation, use the `base81` command (or `python -m base81`). The CLI supports `encode`, `decode`, `info`, `help`, and `completion` commands.

### Encode

```bash
base81 encode [OPTIONS] [FILE...]
```

Encodes binary data to base81/62 text. Reads from stdin if no file given and stdin is not a terminal.

#### Options

| Option | Description |
|--------|-------------|
| `-i, --input FILE` | Input file (default: stdin) |
| `-o, --output FILE` | Output file (default: stdout) |
| `-d, --output-dir DIR` | Output directory for batch processing |
| `-f, --force` | Overwrite existing output files |
| `-w, --line-width COLS` | Wrap output at COLS characters |
| `-b, --block-size N` | Bytes per block: 3, 5, 7 (default: 7) |
| `-a, --alphabet TYPE` | `standard` (81 chars) or `url` (62 chars) |
| `-H, --header` | Prepend self‑describing header (`^b81:...^`) |
| `-s, --stream` | Streaming mode (constant memory) for large files |
| `--buffer-size BYTES` | Buffer size for streaming (default: 64KB) |
| `-j, --jobs N` | Parallel jobs when encoding multiple files |
| `--benchmark` | Run a 10MB performance benchmark |
| `--dry-run` | Preview output size without writing any file |
| `-q, --quiet` | Suppress progress indicators |
| `-v, --verbose` | Increase verbosity |

#### Examples

```bash
# Encode a single file
base81 encode document.pdf -o document.b81

# Encode with header for auto-detection
base81 encode --header data.bin | base81 decode --header > restored.bin

# Encode multiple files in parallel
base81 encode *.bin -d encoded/ -j 4

# Streaming mode for huge files (no memory spike)
base81 encode --stream huge_video.mp4 -o video.b81

# Benchmark encode performance
base81 encode --benchmark --block-size 7

# Preview output size
base81 encode --dry-run large.bin
```

### Decode

```bash
base81 decode [OPTIONS] [FILE...]
```

Decodes base81/62 text back to binary.

#### Options

| Option | Description |
|--------|-------------|
| `-i, --input FILE` | Input file (default: stdin) |
| `-o, --output FILE` | Output file (default: stdout) |
| `-d, --output-dir DIR` | Output directory for batch processing |
| `-f, --force` | Overwrite existing output files |
| `-b, --block-size N` | Override codec detection (3,5,7) |
| `-a, --alphabet TYPE` | Override codec detection (`standard` or `url`) |
| `-H, --header` | Parse self‑describing header for codec |
| `--ignore-ws` | Strip spaces, tabs, newlines from input |
| `--no-canonical-check` | Disable tail validation (**NOT recommended**) |
| `-m, --max-input-length N` | Reject inputs longer than N chars (DoS protection) |
| `-s, --stream` | Streaming mode (constant memory) |
| `--buffer-size BYTES` | Buffer size for streaming (default: 64KB) |
| `--dry-run` | Preview output size |
| `-q, --quiet` | Suppress progress indicators |
| `-v, --verbose` | Increase verbosity |

#### Examples

```bash
# Decode a file
base81 decode document.b81 -o restored.pdf

# Auto-detect codec from header
base81 decode --header data.b81

# Handle wrapped/whitespace-laden input
base81 decode --ignore-ws wrapped.txt

# Dry-run to estimate output
base81 decode --dry-run huge.b81
```

### Info

```bash
base81 info [FILE]
```

Displays codec information and optional file analysis (header detection).

```bash
base81 info                      # show registered codecs
base81 info file_with_header.b81 # parse and display header
```

### Help

```bash
base81 help [COMMAND]
```

Prints detailed help. Without a command, shows full help message.

### Shell Completion

```bash
base81 completion install      # auto-detect shell and install
base81 completion bash         # print bash activation script
base81 completion zsh          # print zsh activation script
base81 completion fish         # print fish activation script
base81 completion tcsh         # print tcsh activation script
```

Requires the optional `argcomplete` package (`pip install base81[cli]`). After installation, restart your shell or source the rc file.

### Configuration File

Persistent defaults can be set in `~/.base81rc` using JSON or `KEY=VALUE` format. CLI arguments override config values.

```json
{"block_size": 7, "alphabet": "url", "quiet": true}
```

or

```
block_size=7
alphabet=standard
quiet=true
```

### Exit Codes

- **0** – Success  
- **1** – Error (invalid input, corruption, etc.)  
- **130** – Interrupted (Ctrl+C)

### Environment Variables

- `SHELL` – Used for auto‑detection in `completion install`  
- `NO_COLOR` – Disables ANSI color output

****

## Performance Characteristics

| Operation | Throughput | Notes |
|-----------|------------|-------|
| Encode (7‑byte blocks) | ~200 MB/s | Single‑threaded, large input |
| Decode (7‑byte blocks) | ~200 MB/s | Single‑threaded, large input |
| Streaming overhead | < 5% vs one‑shot | Constant memory usage |
| Memory (streaming) | < 8 KB typical | Configurable buffer cap |

Benchmark your system with `base81 encode --benchmark`.

****

## Error Handling Best Practices

### Canonical Validation (Always Enabled)

```python
# Good - catches malicious padding
decode("A")  # ValidationError: non-canonical tail

# Bad - would decode "A" to 0x00 0x00 ... 0x01 if validation disabled
decode("A", validate_canonical=False)  # Don't do this
```

### Buffer Limits for Streaming

```python
# Protect against memory exhaustion
encoder = Encoder(max_buffer=1024*1024)  # 1MB limit
try:
    encoder.update(huge_data)
except BoundaryError:
    # Log and abort or retry with larger limit
    logger.error("Input exceeds buffer capacity")
```

### Whitespace Handling

```python
# For wrapped output (e.g., emails, config files)
decoded = decode(wrapped_string, ignore_whitespace=True)

# For strict validation (e.g., API payloads)
decoded = decode(api_string, ignore_whitespace=False)  # Raises on whitespace
```

****

## Common Patterns

### Pattern 1: File with Header

```python
from base81 import encode, make_header

data = open("file.bin", "rb").read()
encoded = make_header(7, "standard") + encode(data)
open("file.b81", "w").write(encoded)
```

### Pattern 2: Network Streaming

```python
from base81 import Encoder, Decoder

# Sender
enc = Encoder(max_buffer=8192)
for chunk in network_stream:
    encoded_chunk = enc.update(chunk)
    socket.send(encoded_chunk.encode())
socket.send(enc.finalize().encode())

# Receiver
dec = Decoder(max_buffer=8192)
while chunk := socket.recv(1024):
    data = dec.update(chunk.decode())
    process(data)
process(dec.finalize())
```

### Pattern 3: Database Key Encoding

```python
# URL-safe keys for database indexes
from base81 import encode

user_id = 123456789
key = encode(user_id.to_bytes(8, 'big'), block_size=5, alphabet_type="url")
# Safe for: /api/users/{key}, DNS labels, JSON
```

### Pattern 4: Batch Processing with Limits

```python
from base81 import decode, BoundaryError

def safe_decode_many(strings, max_total_chars=1024*1024):
    results = []
    total = 0
    for s in strings:
        try:
            results.append(decode(s, max_input_length=1024))
            total += len(s)
            if total > max_total_chars:
                raise BoundaryError("Batch quota exceeded")
        except BoundaryError as e:
            log_error(f"Skipping {s[:50]}: {e}")
    return results
```

****

## Migration from Base64

| Feature | Base64 | Base81/62 |
|---------|--------|-----------|
| Alphabet size | 64 | 62 (url) or 81 (standard) |
| Density | 75% | 78% (url) or 84% (standard) |
| Padding | `=` padding (non‑canonical) | No padding (canonical tails) |
| URL‑safe | `-` and `_` variants | Native alphabet |
| Streaming | Yes | Yes (with memory limits) |
| Self‑describing | No | Optional header |

Migration example:

```python
# Before (base64)
import base64
encoded = base64.urlsafe_b64encode(data).decode().rstrip("=")

# After (base81)
from base81 import encode
encoded = encode(data, block_size=7, alphabet_type="url")
```

****

## Limitations

- Maximum block size: 7 bytes (standard), 5 bytes (url) due to 16‑bit precomputed powers  
- Not space‑optimized for tiny data: Headers add ~10 bytes overhead  
- Standard alphabet not safe for: Domain names, JSON keys (use URL alphabet)  
- No built‑in compression: Use `zlib` before encoding for text data

****

## Verification

Verify the installation and see available codecs:

```bash
base81 info
```

Run a performance benchmark:

```bash
base81 encode --benchmark
```

****

## License

MIT

****

## References

- RFC 4648 (Base64, Base32)  
- Base62 encoding (used in URL shorteners)  
- Ascii85 / Base85 (higher density, special chars)

****

## Version History

- **0.1.0:** Initial release with standard/url alphabets, block sizes 3/5/7, streaming API, and full‑featured CLI
