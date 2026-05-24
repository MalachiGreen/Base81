# Copyright (c) 2026 Malachi Green
# SPDX-License-Identifier: MIT

"""
Exception hierarchy for Base81 codec.

CodecError          - Root, all codec-specific errors
├── ValidationError - Canonical violation, bad alphabet chars, missing header
├── CorruptStreamError - Malformed blocks, overflow, structural misalignment
└── BoundaryError  - Buffer limits exceeded (protection against DoS/memory exhaustion)
"""

class CodecError(Exception):
    """Root exception for all codec architectural errors."""

class ValidationError(CodecError):
    """Raised when canonical bounds checks or token validation checks fail."""

class CorruptStreamError(CodecError):
    """Raised on malformed blocks or structural alignment defects."""

class BoundaryError(CodecError):
    """Raised when protective firewall thresholds or buffer limits are breached."""