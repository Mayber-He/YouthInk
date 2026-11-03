"""Guards for the removed legacy hash encoder and the test-only fake encoder."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import SimpleNamespace

from app.services.embedding import encoder as enc


def test_legacy_hash_encoder_is_removed() -> None:
    assert not hasattr(enc, "encode_text_legacy_hash_sync")
    source = Path(enc.__file__).read_text(encoding="utf-8")
    assert "jieba" not in source
    assert "hashlib" not in source
    # Dimension constants stay: vector_store uses them to recognise old files.
    assert enc.LEGACY_EMBEDDING_DIM == 256
    assert enc.LEGACY_EMBEDDING_MODEL_ID == "hash-ngram-256"
    assert enc.LEGACY_EMBEDDING_VERSION == "hash-ngram-256-v1"


def test_fake_encoder_is_deterministic_normalized_and_sized() -> None:
    first = enc.encode_text_sync("江边黄昏")
    second = enc.encode_text_sync("江边黄昏")
    assert first == second
    assert len(first) == enc.EMBEDDING_DIM
    assert any(value != 0.0 for value in first)
    assert math.isclose(sum(value * value for value in first), 1.0, rel_tol=1e-6)


def test_fake_encoder_blank_text_is_zero_vector() -> None:
    assert enc.encode_text_sync("   \n\t") == [0.0] * enc.EMBEDDING_DIM


def test_fake_encoder_keeps_similar_texts_closer() -> None:
    similar = enc.cosine_similarity(
        enc.encode_text_sync("江边黄昏"), enc.encode_text_sync("江边黄昏照")
    )
    different = enc.cosine_similarity(
        enc.encode_text_sync("江边黄昏"), enc.encode_text_sync("今天股市行情上涨")
    )
    assert similar > different
    assert similar > 0.5


def _load_reindex_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "reindex_embeddings.py"
    spec = importlib.util.spec_from_file_location(
        "reindex_embeddings_under_test", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_reindex_compare_uses_current_encoder_only(monkeypatch, capsys) -> None:
    module = _load_reindex_module()
    assert not hasattr(module, "encode_text_legacy_hash_sync")
    assert not hasattr(module, "LEGACY_EMBEDDING_DIM")
    monkeypatch.setattr(
        module,
        "get_embedding_runtime_status",
        lambda: SimpleNamespace(ready=True, error=None),
    )
    monkeypatch.setattr(
        module,
        "encode_texts_sync",
        lambda texts: [[1.0] + [0.0] * (module.EMBEDDING_DIM - 1) for _ in texts],
    )
    chapters = [
        {
            "_novel_uid": "novel_test",
            "chapter_id": 1,
            "pieces": ["甲片段", "乙片段"],
        }
    ]

    module._print_comparison(chapters, ["查询"])

    out = capsys.readouterr().out
    assert "旧" not in out
    assert "bge-m3" in out
    assert "甲片段" in out and "乙片段" in out


def test_reindex_compare_skips_when_model_unavailable(monkeypatch, capsys) -> None:
    module = _load_reindex_module()
    monkeypatch.setattr(
        module,
        "get_embedding_runtime_status",
        lambda: SimpleNamespace(ready=False, error="模型缺失"),
    )

    def _unexpected(_texts):
        raise AssertionError("encode must not run when the model is unavailable")

    monkeypatch.setattr(module, "encode_texts_sync", _unexpected)
    chapters = [
        {"_novel_uid": "novel_test", "chapter_id": 1, "pieces": ["甲片段"]}
    ]

    module._print_comparison(chapters, ["查询"])

    out = capsys.readouterr().out
    assert "模型缺失" in out
    assert "旧" not in out
