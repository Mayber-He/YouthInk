"""Shared test fixtures.

Tests must not depend on the multi-hundred-megabyte bge-m3 ONNX files. The
autouse fixture installs an explicit deterministic 1024-dim fake encoder; tests
that exercise the real ONNX path clear the override themselves.
"""

from __future__ import annotations

import pytest

from app.services.embedding import encoder as embedding_encoder


class _DeterministicTestEncoder:
    def encode(self, texts: list[str]) -> list[list[float]]:
        return [
            embedding_encoder.encode_text_legacy_hash_sync(
                text, embedding_encoder.EMBEDDING_DIM
            )
            for text in texts
        ]


@pytest.fixture(autouse=True)
def use_fake_embedding_encoder():
    previous = embedding_encoder._encoder_override
    embedding_encoder.set_encoder_override(_DeterministicTestEncoder())
    yield
    embedding_encoder.set_encoder_override(previous)
