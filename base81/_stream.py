# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Streaming encoder/decoder with memory protection.

Encoder:
- Accumulates bytes until full block (fn bytes) ready
- Emits char groups as they complete
- Finalize() handles remainder with minimal char tail

Decoder:
- Accumulates chars until full group (fk chars) or tail possible
- Uses deque for chunk management, _work buffer for partial parsing
- Memory limits: max_input_length (total chars), max_buffer (pending data)
- Requires max_buffer ≥ fk + max_tail for safety

Buffer limits:
- Prevents memory exhaustion from malicious incremental input
- BoundaryError raised when limit exceeded, state preserved for diagnostics
- Caller can inspect via diagnostics() and recover or abort

Whitespace handling:
- ignore_whitespace=True removes all spaces/tabs/newlines (for wrapped output)
- Otherwise raises ValidationError on any whitespace
"""

from collections import deque
from typing import Optional, Dict, Any, Deque
from ._codecs import CODECS, LOOKUPS
from ._math import int_to_radix, radix_to_int, bytes_to_int, int_to_bytes, POW
from ._alphabet import _WS_REMOVE_TABLE
from ._exceptions import ValidationError, CorruptStreamError, BoundaryError


class Encoder:
    """Streaming encoder with buffer limits."""

    def __init__(self, *, block_size: int = 7, alphabet_type: str = "standard",
                 max_input_length: Optional[int] = None,
                 max_buffer: int = 1048576) -> None:
        cfg = CODECS.get((alphabet_type, block_size))
        if cfg is None:
            raise ValidationError("unknown codec")
        if max_input_length is not None and (isinstance(max_input_length, bool) or not isinstance(max_input_length, int) or max_input_length <= 0):
            raise ValidationError("max_input_length must be positive int")
        if max_buffer is not None and (isinstance(max_buffer, bool) or not isinstance(max_buffer, int) or max_buffer <= 0):
            raise ValidationError("max_buffer must be positive int")

        self._cfg = cfg
        self._ac = LOOKUPS[alphabet_type]
        self._buf = bytearray()
        self._total = 0
        self._max_input = max_input_length
        self._max_buf = max_buffer

    def diagnostics(self) -> Dict[str, int]:
        """Return internal state: buffer_len, total_bytes processed."""
        return {"buffer_len": len(self._buf), "total_bytes": self._total}

    def update(self, data: bytes) -> str:
        """Process more input bytes, return encoded chars (may be empty)."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("bytes required")
        if self._max_input is not None and self._total + len(data) > self._max_input:
            raise BoundaryError("input limit exceeded")
        if self._max_buf is not None and len(self._buf) + len(data) > self._max_buf:
            raise BoundaryError("buffer limit exceeded")

        self._total += len(data)
        self._buf.extend(data)

        fn, fk = self._cfg["full_n"], self._cfg["full_k"]
        ready = (len(self._buf) // fn) * fn
        if ready == 0:
            return ""
        chunk = self._buf[:ready]
        self._buf = self._buf[ready:]
        return ''.join(
            int_to_radix(bytes_to_int(bytes(chunk[i:i+fn])), fk, self._ac)
            for i in range(0, ready, fn)
)

    def finalize(self) -> str:
        """Flush remaining bytes, return final encoded chars."""
        if not self._buf:
            return ""
        r = len(self._buf)
        k = self._cfg["tail_enc"][r]
        val = bytes_to_int(bytes(self._buf))
        self._buf.clear()
        return int_to_radix(val, k, self._ac)


class Decoder:
    """Streaming decoder with buffer limits and canonical validation."""

    def __init__(self, *, ignore_whitespace: bool = False, validate_canonical: bool = True,
                 block_size: int = 7, max_input_length: Optional[int] = None,
                 max_buffer: int = 1048576, alphabet_type: str = "standard") -> None:
        cfg = CODECS.get((alphabet_type, block_size))
        if cfg is None:
            raise ValidationError("unknown codec")
        if max_input_length is not None and (isinstance(max_input_length, bool) or not isinstance(max_input_length, int) or max_input_length <= 0):
            raise ValidationError("max_input_length must be positive int")
        if max_buffer is not None and (isinstance(max_buffer, bool) or not isinstance(max_buffer, int) or max_buffer <= 0):
            raise ValidationError("max_buffer must be positive int")

        fk, mt = cfg["full_k"], cfg["max_tail"]
        if max_buffer is not None and max_buffer < fk + mt:
            raise ValidationError(f"max_buffer too small (need ≥ {fk+mt})")

        self._cfg = cfg
        self._ac = LOOKUPS[alphabet_type]
        self._chunks: Deque[str] = deque()
        self._buf_len = 0
        self._work = ""
        self._ignore_ws = ignore_whitespace
        self._canon = validate_canonical
        self._fk = fk
        self._fn = cfg["full_n"]
        self._mt = mt
        self._td = cfg["tail_dec"]
        self._total_chars = 0
        self._max_input = max_input_length
        self._max_buf = max_buffer

    def diagnostics(self) -> Dict[str, Any]:
        """Return internal state: buffer_len, total_chars, chunks pending."""
        return {
            "buffer_len": self._buf_len + len(self._work),
            "total_chars": self._total_chars,
            "chunks": len(self._chunks),
        }

    def update(self, s: str) -> bytes:
        """Process more input chars, return decoded bytes (may be empty)."""
        if not isinstance(s, str):
            raise TypeError("str required")
        if self._max_input is not None and self._total_chars + len(s) > self._max_input:
            raise BoundaryError("input limit exceeded")

        chunk = s if not self._ignore_ws else s.translate(_WS_REMOVE_TABLE)
        if not self._ignore_ws:
            for i, ch in enumerate(chunk):
                if ch in ' \t\n\r':
                    raise ValidationError(f"whitespace at {i}")
        if not chunk:
            return b''

        if self._max_buf is not None:
            total_pending = len(self._work) + self._buf_len + len(chunk)
            threshold = self._fk + self._mt
            if total_pending >= threshold:
                loops = (total_pending - self._mt) // self._fk
                final = total_pending - loops * self._fk
            else:
                final = total_pending
            if final > self._max_buf:
                raise BoundaryError("buffer limit exceeded")

        self._total_chars += len(s)
        self._chunks.append(chunk)
        self._buf_len += len(chunk)

        out = bytearray()
        limit = POW[256][self._fn]

        while self._buf_len + len(self._work) >= self._fk + self._mt:
            while len(self._work) < self._fk and self._chunks:
                nxt = self._chunks.popleft()
                self._buf_len -= len(nxt)
                self._work += nxt
            if len(self._work) < self._fk:
                break
            block = self._work[:self._fk]
            self._work = self._work[self._fk:]
            val = radix_to_int(block, self._ac, self._fk)
            if val >= limit:
                raise CorruptStreamError("block overflow")
            out.extend(int_to_bytes(val, self._fn))

        return bytes(out)

    def finalize(self) -> bytes:
        """Flush remaining chars, validate tail, return final decoded bytes."""
        out = bytearray()
        buf = self._work + ''.join(self._chunks)
        limit = POW[256][self._fn]

        while len(buf) >= self._fk:
            block = buf[:self._fk]
            buf = buf[self._fk:]
            val = radix_to_int(block, self._ac, self._fk)
            if val >= limit:
                raise CorruptStreamError("block overflow")
            out.extend(int_to_bytes(val, self._fn))

        if buf:
            r = len(buf)
            if r not in self._td:
                raise CorruptStreamError("bad tail")
            bc = self._td[r]
            val = radix_to_int(buf, self._ac, r)
            if val >= POW[256][bc]:
                raise CorruptStreamError("tail overflow")
            tres = int_to_bytes(val, bc)
            if self._canon:
                expected = int_to_radix(bytes_to_int(tres), r, self._ac)
                if buf != expected:
                    raise ValidationError("non-canonical tail")
            out.extend(tres)

        self._chunks.clear()
        self._work = ""
        self._buf_len = 0
        return bytes(out)