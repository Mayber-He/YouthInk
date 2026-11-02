"""bge-m3 ONNX embedding encoder (CPU, lazily loaded, globally reused).

The legacy 256-dim hashed encoder is kept as an explicit, test/reindex-only helper.
Production code never falls back to it: a missing or broken model raises
``EmbeddingModelUnavailable`` and callers surface that error to the user.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

import jieba

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_ID = "bge-m3-onnx-fp32"
EMBEDDING_VERSION = "bge-m3-onnx-fp32-1024-v1"
EMBEDDING_DIM = 1024
LEGACY_EMBEDDING_MODEL_ID = "hash-ngram-256"
LEGACY_EMBEDDING_VERSION = "hash-ngram-256-v1"
LEGACY_EMBEDDING_DIM = 256
DEFAULT_MAX_LENGTH = 512
DEFAULT_BATCH_SIZE = 8


class EmbeddingModelUnavailable(RuntimeError):
    """Raised when the ONNX model or tokenizer cannot be used.

    Callers must show this error; they must not fall back to another vector space.
    """


@dataclass(frozen=True)
class EmbeddingRuntimeStatus:
    model_id: str
    dimension: int
    version: str
    ready: bool
    error: str | None
    model_path: str
    tokenizer_path: str
    max_length: int

    def as_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "dimension": self.dimension,
            "version": self.version,
            "ready": self.ready,
            "error": self.error,
            "model_path": self.model_path,
            "tokenizer_path": self.tokenizer_path,
            "max_length": self.max_length,
        }


class _BatchEncoder(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class OnnxEmbeddingConfig:
    model_path: Path
    tokenizer_path: Path
    max_length: int = DEFAULT_MAX_LENGTH
    batch_size: int = DEFAULT_BATCH_SIZE

    @classmethod
    def from_app_config(cls) -> "OnnxEmbeddingConfig":
        from app.core.config import get_config

        cfg = get_config()
        return cls(
            model_path=cfg.bge_m3_dir / "model.onnx",
            tokenizer_path=cfg.bge_m3_dir / "tokenizer.json",
            max_length=cfg.embedding_max_length,
            batch_size=cfg.embedding_batch_size,
        )


def _validate_model_file(path: Path, kind: str) -> None:
    if not path.exists():
        raise EmbeddingModelUnavailable(f"{kind}不存在：{path}")
    size = path.stat().st_size
    if size < 1024:
        raise EmbeddingModelUnavailable(
            f"{kind}是占位文件（{size} 字节），请放入真实 bge-m3 模型文件：{path}"
        )
    head = path.read_bytes()[:64]
    if b"YOUTHINK_ONNX_PLACEHOLDER" in head:
        raise EmbeddingModelUnavailable(f"{kind}仍是占位文件：{path}")


class OnnxEmbeddingEncoder:
    """Lazily loaded bge-m3 ONNX encoder.

    - CPUExecutionProvider only.
    - Tokenizer truncates to ``max_length`` (<= 512).
    - Accepts 3-D last_hidden_state (CLS pooling) or 2-D sentence embeddings.
    - Always returns L2-normalized 1024-dim vectors.
    """

    def __init__(self, config: OnnxEmbeddingConfig) -> None:
        self.config = config
        self._session = None
        self._tokenizer = None
        self._input_names: list[str] = []
        self._output_name = ""
        self._loaded = False
        self._lock = Lock()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if self.config.max_length > DEFAULT_MAX_LENGTH:
                raise EmbeddingModelUnavailable(
                    f"max_length 不能超过 {DEFAULT_MAX_LENGTH}，当前为 {self.config.max_length}"
                )
            _validate_model_file(self.config.model_path, "ONNX 模型")
            _validate_model_file(self.config.tokenizer_path, "分词器")

            try:
                import onnxruntime as ort
            except Exception as exc:  # pragma: no cover - dependency error path
                raise EmbeddingModelUnavailable(f"onnxruntime 不可用：{exc}") from exc
            try:
                from tokenizers import Tokenizer
            except Exception as exc:  # pragma: no cover - dependency error path
                raise EmbeddingModelUnavailable(f"tokenizers 不可用：{exc}") from exc

            try:
                tokenizer = Tokenizer.from_file(str(self.config.tokenizer_path))
                tokenizer.enable_truncation(max_length=self.config.max_length)
                pad_token = (
                    tokenizer.token_to_id("<pad>")
                    if tokenizer.token_to_id("<pad>") is not None
                    else tokenizer.token_to_id("[PAD]")
                )
                tokenizer.enable_padding(pad_id=pad_token or 0, pad_token="<pad>")
            except Exception as exc:
                raise EmbeddingModelUnavailable(
                    f"分词器加载失败（{self.config.tokenizer_path}）：{exc}"
                ) from exc

            try:
                session = ort.InferenceSession(
                    str(self.config.model_path),
                    providers=["CPUExecutionProvider"],
                )
            except Exception as exc:
                raise EmbeddingModelUnavailable(
                    f"ONNX 模型加载失败（{self.config.model_path}）：{exc}"
                ) from exc

            inputs = session.get_inputs()
            names = [item.name for item in inputs]
            if "input_ids" not in names or "attention_mask" not in names:
                raise EmbeddingModelUnavailable(
                    f"ONNX 模型缺少 input_ids/attention_mask，实际输入：{names}"
                )
            unknown = [name for name in names if name not in ("input_ids", "attention_mask", "token_type_ids")]
            if unknown:
                raise EmbeddingModelUnavailable(
                    f"ONNX 模型包含未支持的输入：{unknown}"
                )
            outputs = session.get_outputs()
            if not outputs:
                raise EmbeddingModelUnavailable("ONNX 模型没有输出")
            # BAAI/bge-m3 exports both token_embeddings (3-D) and
            # sentence_embedding (2-D, already CLS-pooled + L2-normalized).
            # Prefer the dedicated sentence output; fall back to a 2-D output,
            # then to the first output (CLS pooling is applied in _encode_batch).
            preferred = next(
                (
                    item
                    for item in outputs
                    if any(key in item.name.lower() for key in ("sentence", "dense", "pool"))
                ),
                None,
            )
            if preferred is None:
                preferred = next(
                    (item for item in outputs if len(item.shape or ()) == 2),
                    outputs[0],
                )
            self._tokenizer = tokenizer
            self._session = session
            self._input_names = names
            self._output_name = preferred.name
            self._loaded = True
            logger.info(
                "embedding model loaded: %s inputs=%s output=%s max_length=%s",
                self.config.model_path,
                names,
                preferred.name,
                self.config.max_length,
            )

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._ensure_loaded()
        assert self._tokenizer is not None and self._session is not None
        results: list[list[float]] = []
        batch_size = max(1, min(self.config.batch_size, 64))
        for start in range(0, len(texts), batch_size):
            results.extend(self._encode_batch(texts[start : start + batch_size]))
        return results

    def _encode_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            import numpy as np

            encodings = self._tokenizer.encode_batch(texts)
            input_ids = np.asarray([enc.ids for enc in encodings], dtype=np.int64)
            attention_mask = np.asarray(
                [enc.attention_mask for enc in encodings], dtype=np.int64
            )
            feeds: dict[str, object] = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
            }
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = np.zeros_like(input_ids)
            raw = self._session.run([self._output_name], feeds)[0]
        except EmbeddingModelUnavailable:
            raise
        except Exception as exc:
            raise EmbeddingModelUnavailable(f"向量推理失败：{exc}") from exc

        arr = np.asarray(raw)
        if arr.ndim == 3:
            # bge-m3 dense 约定：取 [CLS] 位置的 last hidden state。
            arr = arr[:, 0, :]
        elif arr.ndim != 2:
            raise EmbeddingModelUnavailable(
                f"ONNX 输出维度不支持：shape={list(arr.shape)}（期望 3 维 last_hidden_state 或 2 维句向量）"
            )
        if arr.shape[1] != EMBEDDING_DIM:
            raise EmbeddingModelUnavailable(
                f"模型输出维度为 {arr.shape[1]}，期望 {EMBEDDING_DIM}；请使用 bge-m3 1024 维模型"
            )
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        normalized = arr / np.maximum(norms, 1e-12)
        return normalized.astype(float).tolist()


_encoder_lock = Lock()
_encoder: OnnxEmbeddingEncoder | None = None
_encoder_override: _BatchEncoder | None = None
_last_error: str | None = None


def set_encoder_override(encoder: _BatchEncoder | None) -> None:
    """Test-only hook. Never used by production code paths."""
    global _encoder_override
    _encoder_override = encoder


def reset_encoder() -> None:
    """Drop the cached model (tests or explicit retry after replacing files)."""
    global _encoder, _last_error
    with _encoder_lock:
        _encoder = None
        _last_error = None


def _get_encoder() -> OnnxEmbeddingEncoder:
    global _encoder, _last_error
    if _encoder is None:
        with _encoder_lock:
            if _encoder is None:
                try:
                    _encoder = OnnxEmbeddingEncoder(OnnxEmbeddingConfig.from_app_config())
                    _last_error = None
                except Exception as exc:
                    _last_error = str(exc)
                    logger.exception("embedding encoder initialization failed")
                    raise
    return _encoder


def encode_texts_sync(texts: list[str]) -> list[list[float]]:
    """Encode a batch with the configured encoder, or raise EmbeddingModelUnavailable."""
    global _last_error
    if _encoder_override is not None:
        return _encoder_override.encode(texts)
    try:
        return _get_encoder().encode(texts)
    except EmbeddingModelUnavailable as exc:
        _last_error = str(exc)
        logger.warning("embedding unavailable: %s", exc)
        raise
    except Exception as exc:
        _last_error = str(exc)
        logger.exception("embedding inference failed")
        raise EmbeddingModelUnavailable(f"向量编码失败：{exc}") from exc


def encode_text_sync(text: str) -> list[float]:
    vectors = encode_texts_sync([text])
    if not vectors:
        raise EmbeddingModelUnavailable("向量编码返回空结果")
    return vectors[0]


def get_embedding_runtime_status(probe: bool = False) -> EmbeddingRuntimeStatus:
    """Validate model files; with ``probe`` also load ONNX/tokenizer and encode once.

    Retrieval call sites keep the cheap check (``probe=False``) so they never
    block on a model load. The settings status endpoint uses ``probe=True`` to
    prove that the files can actually be loaded and used.
    """
    global _last_error
    config = OnnxEmbeddingConfig.from_app_config()
    error: str | None = None
    try:
        _validate_model_file(config.model_path, "ONNX 模型")
        _validate_model_file(config.tokenizer_path, "分词器")
        # The placeholder check above catches the known stub; parse the JSON header cheaply.
        with config.tokenizer_path.open("rb") as fh:
            head = fh.read(4096)
        if b'"model"' not in head and b'"version"' not in head:
            raise EmbeddingModelUnavailable(
                f"分词器 JSON 内容无效：{config.tokenizer_path}"
            )
    except Exception as exc:
        error = str(exc)
    if error is None and probe:
        try:
            # Deliberately bypass the test-only override: status must prove the
            # real files work, not a fake encoder.
            vectors = _get_encoder().encode(["模型自检"])
            if not vectors or len(vectors[0]) != EMBEDDING_DIM:
                raise EmbeddingModelUnavailable("模型自检未返回 1024 维向量")
            _last_error = None
        except Exception as exc:
            error = str(exc)
            _last_error = error
            logger.warning("embedding model probe failed: %s", error)
    if error is None and _last_error:
        error = _last_error
    return EmbeddingRuntimeStatus(
        model_id=EMBEDDING_MODEL_ID,
        dimension=EMBEDDING_DIM,
        version=EMBEDDING_VERSION,
        ready=error is None,
        error=error,
        model_path=str(config.model_path),
        tokenizer_path=str(config.tokenizer_path),
        max_length=config.max_length,
    )


def encode_text_legacy_hash_sync(text: str, dim: int = LEGACY_EMBEDDING_DIM) -> list[float]:
    """Legacy hash encoder, kept only for comparison/tests and old-vector inspection.

    Production writes/reads must not call this: mixing 256-dim hash vectors with
    1024-dim bge-m3 vectors is rejected by the vector store.
    """
    if not text or not text.strip():
        return [0.0] * dim
    vec = [0.0] * dim
    cleaned = text.strip()
    words = [w.strip() for w in jieba.cut_for_search(cleaned) if len(w.strip()) > 0]
    for word in words:
        digest = hashlib.md5(word.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "little") % dim
        sign = 1.0 if (digest[2] & 1) == 0 else -1.0
        vec[idx] += sign * (1.5 if len(word) >= 2 else 0.8)
    for i in range(len(cleaned) - 1):
        bigram = cleaned[i : i + 2]
        if bigram.isspace():
            continue
        digest = hashlib.md5(bigram.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:2], "little") % dim
        sign = 1.0 if (digest[3] & 1) == 0 else -1.0
        vec[idx] += sign * 0.6
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 1e-9:
        vec = [v / norm for v in vec]
    return vec


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Dot product of two L2-normalized vectors; mismatched lengths score 0."""
    if len(vec_a) != len(vec_b):
        return 0.0
    return sum(a * b for a, b in zip(vec_a, vec_b))
