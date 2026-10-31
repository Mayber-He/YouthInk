"""Stable hashes for binding derived data to exact source text."""

from __future__ import annotations

import hashlib


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
