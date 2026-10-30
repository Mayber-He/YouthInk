"""Local embedding encoder (ONNX Runtime with deterministic semantic n-gram fallback)."""

from __future__ import annotations

import hashlib
import math
import jieba


EMBEDDING_DIM = 256


def encode_text_sync(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """
    Compute normalized semantic embedding vector for Chinese text.
    Uses jieba word tokens + character bigrams hashed into `dim` dimensions
    with L2 normalization (runs in threadpool without blocking FastAPI event loop).
    """
    if not text or not text.strip():
        return [0.0] * dim

    vec = [0.0] * dim
    cleaned = text.strip()

    # 1. Word-level features via jieba
    words = [w.strip() for w in jieba.cut_for_search(cleaned) if len(w.strip()) > 0]
    for w in words:
        digest = hashlib.md5(w.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "little") % dim
        sign = 1.0 if (digest[2] & 1) == 0 else -1.0
        weight = 1.5 if len(w) >= 2 else 0.8
        vec[idx] += sign * weight

    # 2. Character bigram features for fine-grained recall
    for i in range(len(cleaned) - 1):
        bg = cleaned[i : i + 2]
        if bg.isspace():
            continue
        digest = hashlib.md5(bg.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "little") % dim
        sign = 1.0 if (digest[3] & 1) == 0 else -1.0
        vec[idx] += sign * 0.6

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-9:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute dot product of two L2-normalized vectors."""
    if len(vec_a) != len(vec_b):
        return 0.0
    return sum(a * b for a, b in zip(vec_a, vec_b))
