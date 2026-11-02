"""Embedding model (bge-m3 ONNX) status checking.

There is no in-app auto-download: the real ONNX weights are large and must be
placed manually. Status is derived from a real load + one-sentence encode, so a
placeholder or malformed file can never be reported as ready.
"""

from __future__ import annotations

from typing import Literal

from app.core.config import get_config
from app.schemas.settings import EmbeddingModelStatus
from app.services.embedding.encoder import get_embedding_runtime_status

DownloadSource = Literal["modelscope", "hf_mirror", "huggingface"]


def check_embedding_model_status(
    preferred_source: DownloadSource = "modelscope",
) -> EmbeddingModelStatus:
    """Validate the real model by loading ONNX/tokenizer and encoding a sentence."""
    cfg = get_config()
    model_dir = cfg.bge_m3_dir
    model_dir.mkdir(parents=True, exist_ok=True)

    runtime = get_embedding_runtime_status(probe=True)
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

    return EmbeddingModelStatus(
        model_id=runtime.model_id,
        ready=False,
        status="error" if runtime.error else "not_downloaded",
        progress=0.0,
        download_source=preferred_source,
        local_path=str(model_dir),
        message=(
            f"请手动放置模型文件到该目录：{model_dir}。"
            "需要 model.onnx、model.onnx_data 与 tokenizer.json，"
            "且必须能通过 ONNX 加载和一次真实编码。"
            + (f" 当前错误：{runtime.error}" if runtime.error else "")
        ),
    )


async def trigger_embedding_download(source: DownloadSource = "modelscope") -> EmbeddingModelStatus:
    """Explicitly refuse fake downloads; direct the user to manual placement."""
    status = check_embedding_model_status(source)
    if status.ready:
        return status.model_copy(update={"message": "模型已就绪，无需下载。"})
    return status.model_copy(
        update={
            "status": "error" if status.status == "error" else "not_downloaded",
            "progress": 0.0,
            "message": (
                f"自动下载未实现，请手动放置模型文件到：{status.local_path}。"
                + (f" 当前校验错误：{status.message}" if status.status == "error" else "")
            ),
        }
    )
