"""Shared test fixtures.

Tests must not depend on the multi-hundred-megabyte bge-m3 ONNX files. The
autouse fixture installs an explicit deterministic 1024-dim fake encoder; tests
that exercise the real ONNX path clear the override themselves.
"""

from __future__ import annotations

import hashlib
import math

import pytest

from app.services.embedding import encoder as embedding_encoder


def _deterministic_hash_vector(text: str, dim: int) -> list[float]:
    """Character-bigram hashed vector: deterministic, L2-normalized, no jieba."""
    cleaned = "".join(text.split())
    if not cleaned:
        return [0.0] * dim
    grams = [cleaned[i : i + 2] for i in range(len(cleaned) - 1)] or [cleaned]
    vector = [0.0] * dim
    for gram in grams:
        digest = hashlib.md5(gram.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "little") % dim
        sign = 1.0 if digest[2] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm > 1e-12:
        vector = [value / norm for value in vector]
    return vector


class _DeterministicTestEncoder:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [
            _deterministic_hash_vector(text, embedding_encoder.EMBEDDING_DIM)
            for text in texts
        ]


@pytest.fixture(autouse=True)
def use_fake_embedding_encoder():
    previous = embedding_encoder._encoder_override
    embedding_encoder.set_encoder_override(_DeterministicTestEncoder())
    yield
    embedding_encoder.set_encoder_override(previous)
