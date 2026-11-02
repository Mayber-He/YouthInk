"""Embedding model (bge-m3-onnx) status checking, source switching, and download management."""

from __future__ import annotations

import asyncio
from typing import Literal

from app.core.config import get_config
from app.schemas.settings import EmbeddingModelStatus
from app.services.embedding.encoder import get_embedding_runtime_status

DownloadSource = Literal["modelscope", "hf_mirror", "huggingface"]

_download_state: dict[str, object] = {
    "status": "not_downloaded",
    "progress": 0.0,
    "source": "modelscope",
    "message": "",
}

REQUIRED_MODEL_FILES = ("model.onnx", "tokenizer.json")


def check_embedding_model_status(
    preferred_source: DownloadSource = "modelscope",
) -> EmbeddingModelStatus:
    """Check if local bge-m3-onnx model files exist or if a background download is running."""
    cfg = get_config()
    model_dir = cfg.bge_m3_dir
    model_dir.mkdir(parents=True, exist_ok=True)

    runtime = get_embedding_runtime_status()
    if runtime.ready:
        return EmbeddingModelStatus(
            model_id=runtime.model_id,
            ready=True,
            status="ready",
            progress=100.0,
            download_source=preferred_source,
            local_path=str(model_dir),
            message=f"本地 Embedding 模型已就绪（{runtime.dimension} 维，max_length={runtime.max_length}）",
        )

    current_status = str(_download_state.get("status", "not_downloaded"))
    progress = float(_download_state.get("progress", 0.0))  # type: ignore[arg-type]
    msg = runtime.error or str(
        _download_state.get("message") or f"请将真实模型文件放入 {model_dir}"
    )

    return EmbeddingModelStatus(
        model_id=runtime.model_id,
        ready=False,
        status="error" if runtime.error else (
            current_status if current_status in ("downloading", "error") else "not_downloaded"
        ),
        progress=progress,
        download_source=preferred_source,
        local_path=str(model_dir),
        message=msg,
    )


async def trigger_embedding_download(source: DownloadSource = "modelscope") -> EmbeddingModelStatus:
    """Start or simulate background preparation of bge-m3-onnx metadata/files."""
    _download_state["source"] = source
    _download_state["status"] = "downloading"
    _download_state["progress"] = 10.0
    _download_state["message"] = f"正在从 {source} 准备模型目录..."

    asyncio.create_task(_background_prepare_task(source))
    return check_embedding_model_status(source)


async def _background_prepare_task(source: DownloadSource) -> None:
    """Background task that prepares lightweight local tokenizer/onnx stub or downloads."""
    try:
        cfg = get_config()
        model_dir = cfg.bge_m3_dir
        model_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.sleep(0.2)
        _download_state["progress"] = 60.0
        _download_state["message"] = f"正在校验 {source} 模型清单..."
        await asyncio.sleep(0.2)

        # Do not create placeholder weights: a fake model.onnx would make the
        # status look healthy while every embedding call fails.
        manifest_path = model_dir / "manifest.json"
        manifest_path.write_text(
            '{"model_id": "bge-m3-onnx-int8", "source": "' + source + '", "dimension": 1024}',
            encoding="utf-8",
        )
        runtime = get_embedding_runtime_status()
        if runtime.ready:
            _download_state["status"] = "ready"
            _download_state["progress"] = 100.0
            _download_state["message"] = "Embedding 模型已就绪"
        else:
            _download_state["status"] = "error"
            _download_state["progress"] = 100.0
            _download_state["message"] = (
                runtime.error
                or "自动下载未实现，请手动放置真实 model.onnx 与 tokenizer.json"
            )
    except Exception as exc:
        _download_state["status"] = "error"
        _download_state["message"] = f"下载失败: {exc}"
