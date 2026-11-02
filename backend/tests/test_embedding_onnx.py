"""bge-m3 ONNX encoder and vector metadata migration tests.

Unit tests never load the real model: onnxruntime.InferenceSession and
tokenizers.Tokenizer.from_file are replaced with tiny deterministic fakes.
The integration test at the bottom is skipped unless a real model is present.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.embedding import encoder as enc
from app.services.embedding.encoder import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_ID,
    EMBEDDING_VERSION,
    LEGACY_EMBEDDING_DIM,
    LEGACY_EMBEDDING_MODEL_ID,
    LEGACY_EMBEDDING_VERSION,
    EmbeddingModelUnavailable,
    OnnxEmbeddingConfig,
    OnnxEmbeddingEncoder,
)


class _FakeTokenizer:
    def __init__(self, ids: list[int] | None = None) -> None:
        self._ids = ids or [101, 202, 303]
        self.padding_enabled = False
        self.truncation_max: int | None = None
        self.batch_count = 0

    def enable_truncation(self, max_length: int) -> None:
        self.truncation_max = max_length

    def enable_padding(self, pad_id: int = 0, pad_token: str = "<pad>") -> None:
        self.padding_enabled = True

    def token_to_id(self, token: str) -> int | None:
        return 0 if token in ("<pad>", "[PAD]") else None

    def encode_batch(self, texts: list[str]) -> list[SimpleNamespace]:
        self.batch_count += 1
        return [
            SimpleNamespace(ids=list(self._ids), attention_mask=[1] * len(self._ids))
            for _ in texts
        ]


class _FakeSession:
    def __init__(
        self,
        output_name: str | list[SimpleNamespace],
        raw_fn,
        input_names: list[str] | None = None,
    ):
        self._outputs = (
            output_name
            if isinstance(output_name, list)
            else [SimpleNamespace(name=output_name, shape=[None, EMBEDDING_DIM])]
        )
        self._raw_fn = raw_fn
        self._input_names = input_names or ["input_ids", "attention_mask"]
        self.run_calls = 0
        self.requested_outputs: list[str] = []

    def get_inputs(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name=name) for name in self._input_names]

    def get_outputs(self) -> list[SimpleNamespace]:
        return self._outputs

    def run(self, output_names, feeds):  # noqa: ANN001
        self.run_calls += 1
        self.requested_outputs.extend(output_names)
        return [self._raw_fn(feeds)]


def _materialize_model_files(tmp_path: Path) -> tuple[Path, Path]:
    """Files pass the placeholder/size gate; loading is monkeypatched."""
    model = tmp_path / "model.onnx"
    tokenizer = tmp_path / "tokenizer.json"
    model.write_bytes(b"onnx" + b"\x00" * 2048)
    tokenizer.write_bytes(b'{"version": "1.0", "model": {}}' + b" " * 2048)
    return model, tokenizer


def _install_fakes(monkeypatch, tmp_path, raw_fn, tokenizer=None, outputs=None):
    model, tokenizer_path = _materialize_model_files(tmp_path)
    fake_tokenizer = tokenizer or _FakeTokenizer()
    session = _FakeSession(outputs or "last_hidden_state", raw_fn)

    from tokenizers import Tokenizer

    monkeypatch.setattr(
        Tokenizer, "from_file", staticmethod(lambda _path: fake_tokenizer)
    )

    import onnxruntime as ort

    monkeypatch.setattr(ort, "InferenceSession", lambda *a, **k: session)
    config = OnnxEmbeddingConfig(
        model_path=model, tokenizer_path=tokenizer_path, max_length=512, batch_size=8
    )
    return OnnxEmbeddingEncoder(config), fake_tokenizer, session


def _three_d_output(feeds):
    import numpy as np

    input_ids = feeds["input_ids"]
    batch = input_ids.shape[0]
    raw = np.zeros((batch, 2, EMBEDDING_DIM), dtype=np.float32)
    # Position 0 (CLS) carries [3, 4]; position 1 carries zeros so mean pooling
    # would produce a different vector and fail the CLS assertion.
    raw[:, 0, 0] = 3.0
    raw[:, 0, 1] = 4.0
    raw[:, 1, 1] = 99.0
    return raw


def test_cls_pooling_and_l2_normalization(monkeypatch, tmp_path):
    encoder, _tokenizer, _session = _install_fakes(
        monkeypatch, tmp_path, _three_d_output
    )
    vectors = encoder.encode(["江边黄昏", "开学的第一天"])
    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_DIM for vector in vectors)
    for vector in vectors:
        assert vector[0] == pytest.approx(0.6, abs=1e-6)
        assert vector[1] == pytest.approx(0.8, abs=1e-6)
        assert math.isclose(sum(v * v for v in vector), 1.0, rel_tol=1e-5)


def test_two_dimensional_embeddings_are_normalized(monkeypatch, tmp_path):
    import numpy as np

    def raw_fn(feeds):
        batch = feeds["input_ids"].shape[0]
        out = np.zeros((batch, EMBEDDING_DIM), dtype=np.float32)
        out[:, 0] = 3.0
        out[:, 1] = 4.0
        return out

    encoder, _tokenizer, _session = _install_fakes(monkeypatch, tmp_path, raw_fn)
    vector = encoder.encode(["黄昏的江边"])[0]
    assert vector[0] == pytest.approx(0.6, abs=1e-6)
    assert vector[1] == pytest.approx(0.8, abs=1e-6)
    assert math.isclose(sum(v * v for v in vector), 1.0, rel_tol=1e-5)


def test_prefers_sentence_embedding_over_token_embeddings(monkeypatch, tmp_path):
    import numpy as np

    def raw_fn(feeds):
        batch = feeds["input_ids"].shape[0]
        out = np.zeros((batch, EMBEDDING_DIM), dtype=np.float32)
        out[:, 0] = 3.0
        out[:, 1] = 4.0
        return out

    outputs = [
        SimpleNamespace(name="token_embeddings", shape=[None, None, EMBEDDING_DIM]),
        SimpleNamespace(name="sentence_embedding", shape=[None, EMBEDDING_DIM]),
    ]
    encoder, _tokenizer, session = _install_fakes(
        monkeypatch, tmp_path, raw_fn, outputs=outputs
    )
    vector = encoder.encode(["江边黄昏"])[0]
    assert session.requested_outputs == ["sentence_embedding"]
    assert vector[0] == pytest.approx(0.6, abs=1e-6)
    assert vector[1] == pytest.approx(0.8, abs=1e-6)


def test_batch_encoding_respects_batch_size(monkeypatch, tmp_path):
    encoder, tokenizer, session = _install_fakes(
        monkeypatch, tmp_path, _three_d_output
    )
    encoder.config = OnnxEmbeddingConfig(
        model_path=encoder.config.model_path,
        tokenizer_path=encoder.config.tokenizer_path,
        max_length=512,
        batch_size=2,
    )
    vectors = encoder.encode(["一", "二", "三", "四", "五"])
    assert len(vectors) == 5
    assert session.run_calls == 3
    assert tokenizer.batch_count == 3
    assert tokenizer.truncation_max == 512


def test_wrong_output_dimension_is_rejected(monkeypatch, tmp_path):
    import numpy as np

    encoder, _tokenizer, _session = _install_fakes(
        monkeypatch,
        tmp_path,
        lambda feeds: np.ones((feeds["input_ids"].shape[0], 512), dtype=np.float32),
    )
    with pytest.raises(EmbeddingModelUnavailable, match="期望 1024"):
        encoder.encode(["开学"])


def test_missing_model_raises_explicit_error(tmp_path):
    encoder = OnnxEmbeddingEncoder(
        OnnxEmbeddingConfig(
            model_path=tmp_path / "missing.onnx",
            tokenizer_path=tmp_path / "missing.json",
        )
    )
    with pytest.raises(EmbeddingModelUnavailable, match="ONNX 模型不存在"):
        encoder.encode(["江边黄昏"])


def test_placeholder_model_raises_explicit_error(tmp_path):
    model = tmp_path / "model.onnx"
    tokenizer = tmp_path / "tokenizer.json"
    model.write_bytes(b"YOUTHINK_ONNX_PLACEHOLDER" + b"\x00" * 2048)
    tokenizer.write_bytes(b'{"version": "1.0", "model": {}}')
    encoder = OnnxEmbeddingEncoder(
        OnnxEmbeddingConfig(model_path=model, tokenizer_path=tokenizer)
    )
    with pytest.raises(EmbeddingModelUnavailable, match="占位文件"):
        encoder.encode(["开学"])


def test_max_length_above_512_is_rejected(tmp_path):
    encoder = OnnxEmbeddingEncoder(
        OnnxEmbeddingConfig(
            model_path=tmp_path / "model.onnx",
            tokenizer_path=tmp_path / "tokenizer.json",
            max_length=1024,
        )
    )
    with pytest.raises(EmbeddingModelUnavailable, match="不能超过 512"):
        encoder.encode(["开学"])


def test_global_encode_wraps_unexpected_failures(monkeypatch):
    previous = enc._encoder_override
    enc.set_encoder_override(None)
    monkeypatch.setattr(
        enc, "_get_encoder", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    try:
        with pytest.raises(EmbeddingModelUnavailable, match="向量编码失败"):
            enc.encode_texts_sync(["开学"])
    finally:
        enc.set_encoder_override(previous)


def test_vector_store_persists_metadata_and_isolates_legacy_space(tmp_path):
    from app.core.config import reset_config_for_testing
    from app.db.vector_store import NovelVectorStore, VectorChunkRecord

    reset_config_for_testing(tmp_path / "data")
    store = NovelVectorStore("novel_embedding_test")

    def record(chapter_id: int, dim: int, version: str, model_id: str):
        vector = [0.0] * dim
        vector[0] = 1.0
        return VectorChunkRecord(
            chunk_id=f"ch_{chapter_id}_ck_1",
            chapter_id=chapter_id,
            chapter_sort_order=float(chapter_id),
            scene_id=None,
            character_ids=[],
            location_id=None,
            story_time="",
            embedding_model_id=model_id,
            text=f"第 {chapter_id} 章片段",
            vector=vector,
            source_hash="hash",
            embedding_dim=dim,
            embedding_version=version,
        )

    new = record(2, EMBEDDING_DIM, EMBEDDING_VERSION, EMBEDDING_MODEL_ID)
    old = record(1, LEGACY_EMBEDDING_DIM, LEGACY_EMBEDDING_VERSION, LEGACY_EMBEDDING_MODEL_ID)
    store.replace_all_chunks([new, old])

    loaded = {r.chapter_id: r for r in store._load_all()}
    assert loaded[2].embedding_dim == EMBEDDING_DIM
    assert loaded[2].embedding_version == EMBEDDING_VERSION
    assert loaded[2].embedding_model_id == EMBEDDING_MODEL_ID
    assert loaded[1].embedding_version == LEGACY_EMBEDDING_VERSION

    assert store.incompatible_chapter_ids(
        EMBEDDING_DIM, EMBEDDING_VERSION, EMBEDDING_MODEL_ID
    ) == [1]
    assert store.has_incompatible(
        EMBEDDING_DIM, EMBEDDING_VERSION, EMBEDDING_MODEL_ID
    )
    hits = store.search_vectors(
        [1.0] + [0.0] * (EMBEDDING_DIM - 1),
        top_k=8,
        expected_dim=EMBEDDING_DIM,
        expected_version=EMBEDDING_VERSION,
        expected_model_id=EMBEDDING_MODEL_ID,
    )
    assert [rec.chapter_id for rec, _score in hits] == [2]

    # Without expectations both spaces remain visible for inspection.
    all_hits = store.search_vectors([1.0] + [0.0] * (EMBEDDING_DIM - 1), top_k=8)
    assert {rec.chapter_id for rec, _score in all_hits} == {1, 2}


def test_legacy_records_without_metadata_are_inferred_as_256d(tmp_path):
    import json

    from app.core.config import reset_config_for_testing
    from app.db.vector_store import NovelVectorStore

    reset_config_for_testing(tmp_path / "data")
    store = NovelVectorStore("novel_legacy_test")
    store.store_file.write_text(
        json.dumps(
            [
                {
                    "chunk_id": "old",
                    "chapter_id": 1,
                    "chapter_sort_order": 1.0,
                    "scene_id": None,
                    "character_ids": [],
                    "location_id": None,
                    "story_time": "",
                    "embedding_model_id": "bge-m3-onnx-int8",
                    "text": "旧索引",
                    "vector": [0.0] * LEGACY_EMBEDDING_DIM,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loaded = store._load_all()[0]
    assert loaded.embedding_dim == LEGACY_EMBEDDING_DIM
    assert loaded.embedding_version == LEGACY_EMBEDDING_VERSION
    assert store.incompatible_chapter_ids(
        EMBEDDING_DIM, EMBEDDING_VERSION, EMBEDDING_MODEL_ID
    ) == [1]


def _runtime_status(ready: bool, error: str | None = None):
    from app.services.embedding.encoder import EmbeddingRuntimeStatus

    return EmbeddingRuntimeStatus(
        model_id=EMBEDDING_MODEL_ID,
        dimension=EMBEDDING_DIM,
        version=EMBEDDING_VERSION,
        ready=ready,
        error=error,
        model_path="model.onnx",
        tokenizer_path="tokenizer.json",
        max_length=512,
    )


def test_model_status_requires_real_probe_and_never_writes_placeholders(
    monkeypatch, tmp_path
):
    import asyncio
    from types import SimpleNamespace

    from app.services.embedding import manager

    model_dir = tmp_path / "models" / "bge-m3-onnx"
    monkeypatch.setattr(
        manager, "get_config", lambda: SimpleNamespace(bge_m3_dir=model_dir)
    )
    calls = []

    def probe(*, probe=False):
        calls.append(probe)
        return _runtime_status(False, "ONNX 模型不存在")

    monkeypatch.setattr(manager, "get_embedding_runtime_status", probe)
    status = manager.check_embedding_model_status()
    assert calls == [True]
    assert status.ready is False
    assert "请手动放置模型文件到该目录" in status.message
    assert "ONNX 模型不存在" in status.message

    result = asyncio.run(manager.trigger_embedding_download())
    assert result.ready is False
    assert "自动下载未实现" in result.message
    assert not model_dir.exists() or not list(model_dir.iterdir())


def test_model_status_ready_only_after_probe_succeeds(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.services.embedding import manager

    model_dir = tmp_path / "models"
    monkeypatch.setattr(
        manager, "get_config", lambda: SimpleNamespace(bge_m3_dir=model_dir)
    )
    monkeypatch.setattr(
        manager, "get_embedding_runtime_status", lambda *, probe=False: _runtime_status(True)
    )
    status = manager.check_embedding_model_status()
    assert status.ready is True
    assert status.progress == 100.0
    assert "已就绪" in status.message


def test_index_status_marker_persists_reason_and_chapters(tmp_path):
    from app.core.config import reset_config_for_testing
    from app.db.vector_store import NovelVectorStore

    reset_config_for_testing(tmp_path / "data")
    store = NovelVectorStore("novel_index_status_test")
    assert store.read_index_status()["pending_rebuild"] is False

    store.mark_rebuild_pending("向量编码失败：模型缺失", [7, 8])
    status = store.read_index_status()
    assert status["pending_rebuild"] is True
    assert status["reason"] == "向量编码失败：模型缺失"
    assert status["chapters"] == [7, 8]

    store.clear_chapter_pending(7)
    assert store.read_index_status()["chapters"] == [8]
    store.clear_chapter_pending(8)
    assert store.read_index_status()["pending_rebuild"] is False
    assert not store.index_status_file.exists()

    store.index_status_file.write_text(
        '{"pending_rebuild": true, "reason": "bad", "chapters": ["oops"]}',
        encoding="utf-8",
    )
    corrupt = store.read_index_status()
    assert corrupt["pending_rebuild"] is True
    assert "章节字段损坏" in corrupt["reason"]


def test_real_model_semantics_if_available(monkeypatch):
    """Runs only when the real bge-m3 files are installed."""
    from app.core.config import reset_config_for_testing

    # Earlier unit tests point YOUTHINK_DATA_DIR at tmp_path; restore the real
    # backend/data directory so the model present on disk can be exercised.
    monkeypatch.delenv("YOUTHINK_DATA_DIR", raising=False)
    reset_config_for_testing()
    enc.set_encoder_override(None)
    enc.reset_encoder()
    status = enc.get_embedding_runtime_status()
    if not status.ready:
        pytest.skip(f"bge-m3 模型不可用：{status.error}")

    texts = [
        "江边的黄昏照在旧码头上",
        "傍晚的江水映着落日余晖",
        "新学期开学的第一天",
        "今天股市行情大幅上涨",
    ]
    vectors = enc.encode_texts_sync(texts)
    assert len(vectors) == len(texts)
    for vector in vectors:
        assert len(vector) == EMBEDDING_DIM
        assert math.isclose(sum(v * v for v in vector), 1.0, rel_tol=1e-4)

    def sim(a: int, b: int) -> float:
        return sum(x * y for x, y in zip(vectors[a], vectors[b]))

    assert sim(0, 1) > sim(0, 3)
    assert sim(0, 1) > sim(1, 2)
    assert sim(0, 1) == max(
        sim(i, j) for i in range(len(texts)) for j in range(i + 1, len(texts))
    )
