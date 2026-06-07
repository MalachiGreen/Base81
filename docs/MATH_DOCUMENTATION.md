# Base81/62: Mathematical Foundation

## 1. Core Problem

Convert a byte string (base-256 digits) to a base-N string ($N=62$ or $81$) with:
- **Bijection**: Unique encoding/decoding
- **Optimal density**: Minimum characters for given bytes
- **Canonical form**: No leading zeros or ambiguous representations
- **Streaming**: Process partial blocks efficiently

---

## 2. Radix Conversion

### 2.1 Positional Notation

A byte string $b_0 b_1 \dots b_{n-1}$ (big-endian) represents integer:

$$
V = \sum_{i=0}^{n-1} b_i \times 256^{n-1-i}
$$

Similarly, base-N string $c_0 c_1 \dots c_{m-1}$ (big-endian) represents:

$$
V = \sum_{j=0}^{m-1} c_j \times N^{m-1-j}
$$

### 2.2 Direct Conversion

**Bytes → Integer → Base-N**

```python
V = int.from_bytes(data, 'big')
digits = []
while V > 0:
    V, rem = divmod(V, N)
    digits.append(alphabet[rem])
return ''.join(reversed(digits))
```

**Problem**: Integer can be arbitrarily large (up to $256^{\text{bytes}}$). Python handles big ints, but streaming requires block-wise conversion.

---

## 3. Block Decomposition

### 3.1 Fixed-Size Blocks

Process $f_n$ bytes → $f_k$ characters where:
$$
N^{f_k} \geq 256^{f_n} \quad (\text{capacity condition})
$$

**Example (Base81, $f_n=7$):**
- $81^9 = 150,094,635,296,999,121$
- $256^7 = 72,057,594,037,927,936$
- $81^9 / 256^7 \approx 2.083$ (21% headroom)

### 3.2 Why Not Variable-Length Blocks?

Fixed blocks allow streaming without lookahead. Each block is independent.

---

## 4. Tail Handling (The Key Innovation)

### 4.1 The Problem

Last block may have $r$ bytes where $1 \leq r < f_n$. Cannot simply pad to $f_n$ because:
- Padding creates ambiguity (is padding data or filler?)
- Wastes space

### 4.2 Minimal Character Expansion

Find smallest $k$ such that:

$$
N^k \geq 256^r
$$

**Rationale**: $k$ characters must represent any $r$-byte value ($0$ to $256^r - 1$).

**Example (Base81, $r=3$):**
- $81^1 = 81 < 256^3 = 16,777,216$ ❌
- $81^2 = 6,561 < 16,777,216$ ❌
- $81^3 = 531,441 < 16,777,216$ ❌
- $81^4 = 43,046,721 \geq 16,777,216$ ✅
- **Result**: $k = 4$ characters for 3 bytes

### 4.3 Tail Mapping Table

For Base81 ($f_n=7$):

| $r$ (bytes) | min $k$ | $81^k$ | $256^r$ | $k/r$ ratio |
|:---:|:---:|:---:|:---:|:---:|
| 1 | 2 | 6,561 | 256 | 2.0 |
| 2 | 3 | 531,441 | 65,536 | 1.5 |
| 3 | 4 | 43,046,721 | 16,777,216 | 1.33 |
| 4 | 5 | 3,486,784,401 | 4,294,967,296 | 1.25 |
| 5 | 6 | 282,429,536,481 | 1,099,511,627,776 | 1.2 |
| 6 | 8 | 1,853,020,188,851,841 | 281,474,976,710,656 | 1.33 |

*Note: $r=6$ uses $k=8$ (not 7) because $81^7 < 256^6$.*

### 4.4 Canonical Condition

For a tail of $r$ bytes encoded to $k$ chars, the encoding must use the smallest possible integer representation. No leading zero chars except when value is zero.

**Non-canonical example (Base81, $r=1$):**
- Value 0: Canonical `"00"`, non-canonical `"0A"` (leading zero then junk)
- Value 1: Canonical `"01"`, non-canonical `"001"` (extra zero)

**Enforcement:**
```python
canonical = int_to_radix(value, r, alphabet) == encoded_tail
```
Where `int_to_radix` always produces exactly $k$ chars with leading zeros allowed only for zero.

---

## 5. Overflow Prevention

### 5.1 Full Block Overflow

When decoding $f_k$ chars to $f_n$ bytes:

$$
\text{if } value \geq 256^{f_n}: \quad \text{raise CorruptStreamError}
$$

Because $N^{f_k} > 256^{f_n}$ (headroom), some $f_k$-char sequences are invalid.

**Example (Base81, $f_n=7, f_k=9$):**
- Max valid: $256^7 - 1 = 72,057,594,037,927,935$
- Max encodable: $81^9 - 1 = 150,094,635,296,999,120$
- **Overflow values**: $72,057,594,037,927,936$ to $150,094,635,296,999,120$

### 5.2 Tail Overflow

Similarly for tail $k$ chars decoding to $r$ bytes:

$$
\text{if } value \geq 256^r: \quad \text{raise CorruptStreamError}
$$

---

## 6. Density Analysis

### 6.1 Encoding Efficiency

$$
\text{Efficiency} = \frac{\text{bytes} \times 8}{\text{chars} \times \log_2(N)}
$$

| Codec | $N$ | bytes:chars | Efficiency | vs Base64 |
|:---|:---:|:---:|:---:|:---:|
| Base64 | 64 | 3:4 | 75% | baseline |
| Base62 | 62 | 5:7 | 71.4% | -4.8% |
| Base81 | 81 | 7:9 | 77.8% | +3.7% |

**Actual density (including tails):**
For large files, average overhead $\approx (k/r) / (f_n/f_k)$.

- **Base81** (7:9 ratio = 1.2857 chars/byte theoretical):
  - Small files (< 7 bytes): overhead higher (up to 2.0 chars/byte for $r=1$)
  - Large files: approaches 1.2857
- **Base62** (5:7 ratio = 1.4 chars/byte theoretical):
  - Approaches 1.4 asymptotically

### 6.2 Character Distribution

For random bytes, encoded chars are uniformly distributed in alphabet because:
- Bytes uniformly distributed in $[0, 255]$
- Multiplication by base-N mixes bits
- Division/mod operations preserve uniformity

**Proof sketch**: For full blocks, mapping is bijection between $256^{f_n}$ inputs and $N^{f_k}$ outputs (subset). Input uniformity → output uniformity.

---

## 7. Streaming Mathematics

### 7.1 State Machine

Encoder maintains buffer of $< f_n$ bytes. When buffer reaches $f_n$ bytes:
1. Convert $f_n$ bytes → integer $V$
2. Convert $V$ → $f_k$ base-N digits
3. Emit digits, clear buffer

### 7.2 Buffer Invariant

Let $B$ = byte buffer, $0 \leq |B| < f_n$. After processing:
$$
\text{total\_bytes} = \sum \text{input\_sizes}
$$
$$
\text{pending\_bytes} = |B|
$$
`pending_bytes` always $< f_n$ before `finalize()`.

### 7.3 Finalize Operation

Convert remaining $r = |B|$ bytes using tail mapping:
1. Find $k = \text{tail\_enc}[r]$
2. Convert to integer $V$ (big-endian)
3. Convert to $k$ base-N digits (zero-padded to length $k$)
4. Emit digits

---

## 8. Lookup Tables for Performance

### 8.1 Precomputed Powers

$$
\text{POW}[N][e] = N^e \quad \text{for } e = 0..16, N \in \{62, 81, 256\}
$$

Used for:
- Capacity checks: $\text{POW}[N][f_k] \geq \text{POW}[256][f_n]$
- Overflow detection: $value \geq \text{POW}[256][f_n]$
- Tail length search: `while POW[N][k] < POW[256][r]: k++`

### 8.2 Alphabet Mapping

- Forward: `to_char[digit] = character`
- Reverse: `to_idx[char] = digit` ($0..N-1$)

Precomputed once at module load.

---

## 9. Algorithmic Complexity

| Operation | Time | Space |
|:---|:---|:---|
| Encode (full block) | $O(f_n)$ | $O(f_k)$ |
| Decode (full block) | $O(f_k)$ | $O(f_n)$ |
| Tail encode | $O(r \times \log(N))$ | $O(k)$ |
| Tail decode | $O(k \times \log(N))$ | $O(r)$ |
| Streaming per byte | $O(1)$ amortized | $O(f_n + f_k)$ |

**Constants:**
- $f_n \leq 7$, $f_k \leq 9$
- Tails: $r \leq 6$, $k \leq 8$
- All operations effectively $O(1)$ per byte

---

## 10. Security Properties

### 10.1 No Timing Side-Channels
- Alphabet lookup uses $O(1)$ array access (not dict).
- Integer conversion uses fixed-width operations.

### 10.2 Canonical Protection
Prevents "shortest representation" attacks where:
- `"A"` and `"00A"` decode to same bytes
- Attacker inflates message size or hides data

### 10.3 Overflow Rejection
Invalid values (e.g., $81^9 - 1$ decoding to 7 bytes) rejected, preventing:
- Buffer over-reads
- Integer wraparound exploits

### 10.4 Input Bounds
- `max_input_length` prevents memory exhaustion.
- `max_buffer` prevents incremental DoS.

---

## 11. Mathematical Proofs

### Theorem 1: Bijection (Full Blocks)
**Statement**: For fixed $f_n, f_k$ with $N^{f_k} \geq 256^{f_n}$, the mapping $f: [0, 256^{f_n}) \to S \subset [0, N^{f_k})$ is injective.

**Proof**: If two byte sequences produce same integer $V$, they are identical (bytes-to-int is bijection). Base-N conversion is deterministic. Therefore mapping is injective on the subset of $N^{f_k}$ values $< 256^{f_n}$.

### Theorem 2: Tail Uniqueness
**Statement**: For each $r$ ($1 \leq r < f_n$), there exists unique minimal $k$ satisfying $N^k \geq 256^r$.

**Proof**: $N^k$ is monotonic in $k$. Existence guaranteed because $N^0=1 < 256^r$ and $\lim_{k\to\infty} N^k = \infty$. Uniqueness from minimality.

### Theorem 3: Canonical Form Uniqueness
**Statement**: For given $r$ bytes, exactly one $k$-character base-N string satisfies the canonical condition.

**Proof**: Integer $V$ in $[0, 256^r)$ has unique base-N representation with exactly $k$ digits (leading zeros allowed only when $V=0$). The `int_to_radix` function produces exactly this representation.

---

## 12. Reference Implementation Math

```python
def find_min_k(radix: int, r: int) -> int:
    """Find smallest k such that radix^k >= 256^r."""
    k = 1
    while pow(radix, k) < pow(256, r):
        k += 1
    return k

def tail_enc_table(radix: int, fn: int) -> dict:
    """Build tail_enc mapping for given radix and fn."""
    te = {}
    for r in range(1, fn):
        te[r] = find_min_k(radix, r)
    return te

def tail_dec_table(te: dict) -> dict:
    """Build tail_dec inverse mapping."""
    td = {}
    for r, k in te.items():
        td[k] = r
    return td
```

---

## 13. Optimization: Integer Arithmetic

Instead of `pow(256, r)` (exponentiation each time), precompute:

```python
POW256 = [1]
for _ in range(16):
    POW256.append(POW256[-1] * 256)
```

Similarly for $N^k$:

```python
POW81 = [1]
for _ in range(16):
    POW81.append(POW81[-1] * 81)
```

Tail search becomes:

```python
k = 1
while POW81[k] < POW256[r]:
    k += 1
```

---

## 14. Examples

### Example 1: Encode "Hi" (2 bytes) with Base81
- **Bytes**: `0x48 0x69`
- **Integer**: $V = 0x4869 = 18,537$
- **Tail Logic**: $r = 2$ bytes.
  - $81^1=81 < 65536$
  - $81^2=6,561 < 65536$
  - $81^3=531,441 \geq 65536 \implies k=3$
- **Conversion**: Convert 18,537 to base81 digits:
  - $18,537 \div 81 = 228$ rem $69 \to$ digit 69 = `'q'`
  - $228 \div 81 = 2$ rem $66 \to$ digit 66 = `'R'`
  - $2 \div 81 = 0$ rem $2 \to$ digit 2 = `'2'`
- **Digits** (big-endian): `[2, 66, 69]` → **`"2Rq"`**

### Example 2: Decode "2Rq" with Base81
- **Lookup**: $k=3$ chars $\to$ `td[3] = 2` bytes
- **Conversion**: Convert `"2Rq"` from base81:
  - `'2'=2`, `'R'=66`, `'q'=69`
  - $V = ((2 \times 81) + 66) \times 81 + 69 = 18,537$
- **Bytes**: $18,537 = 0x4869 \to$ **`"Hi"`** ✅

---

## 15. Limits and Extensions

**Current limits:**
- $f_n \leq 7$ (bytes) due to POW table size (16 entries)
- $N \leq 81$ (fits in 7-bit digits)
- Max input $\approx 2^{63}$ bytes (limited by Python big ints)

**Extending to larger $f_n$:**
- Need larger POW tables
- Integer conversions become slower but still $O(1)$ per block
- Could support up to $f_n=16$ with $256^{16} \approx 2^{128}$ (Python handles easily)

**Extending to other bases:**
- Any $N$ where $2 \leq N \leq 256$
- Must ensure $N^{f_k} \geq 256^{f_n}$ for chosen $f_n, f_k$
- Character set must be $N$ distinct printable chars excluding `^`

> All formulas and theorems directly correspond to code in `_math.py`, `_codecs.py`, and `_api.py`.
