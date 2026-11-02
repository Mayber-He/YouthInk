"""Global configuration and path management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Application runtime configuration resolved from environment variables."""

    data_dir: Path
    host: str
    port: int
    static_dir: Path
    # bge-m3 ONNX runtime. max_length is capped at 512 by the encoder.
    embedding_max_length: int = 512
    embedding_batch_size: int = 8

    @property
    def global_db_path(self) -> Path:
        return self.data_dir / "global.db"

    @property
    def secret_key_path(self) -> Path:
        return self.data_dir / ".secret.key"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def bge_m3_dir(self) -> Path:
        """Directory of the usable bge-m3 ONNX export.

        The repository receives two different exports:
        - ``models/bge-m3/onnx``: the complete BAAI/bge-m3 export with
          ``model.onnx``, ``model.onnx_data`` and ``tokenizer.json``;
        - ``models/bge-m3-onnx``: an NPU-oriented export that may only contain
          ``bge-m3.onnx``/``bge-m3.onnx.data`` and no tokenizer.
        Prefer the complete directory, while keeping an explicit environment
        override for deployments that use another layout.
        """
        override = os.environ.get("YOUTHINK_EMBEDDING_MODEL_DIR")
        if override:
            return Path(override).resolve()
        complete = self.models_dir / "bge-m3" / "onnx"
        if (complete / "model.onnx").exists() and (complete / "tokenizer.json").exists():
            return complete
        return self.models_dir / "bge-m3-onnx"

    def novel_dir(self, novel_uid: str) -> Path:
        return self.data_dir / novel_uid

    def novel_db_path(self, novel_uid: str) -> Path:
        return self.novel_dir(novel_uid) / "novel.db"

    def novel_vectors_dir(self, novel_uid: str) -> Path:
        return self.novel_dir(novel_uid) / "vectors"

    def novel_backups_dir(self, novel_uid: str) -> Path:
        return self.novel_dir(novel_uid) / "backups"


def load_config() -> AppConfig:
    """Resolve configuration from environment variables with sensible defaults."""
    backend_root = Path(__file__).resolve().parent.parent.parent
    default_data_dir = backend_root / "data"
    raw_data_dir = os.environ.get("YOUTHINK_DATA_DIR")
    data_dir = Path(raw_data_dir).resolve() if raw_data_dir else default_data_dir

    host = os.environ.get("YOUTHINK_HOST", "0.0.0.0")
    port = int(os.environ.get("YOUTHINK_PORT", "8000"))
    # ONNX Runtime configuration (CPU only). Keep max_length <= 512.
    try:
        embedding_max_length = min(
            512, max(8, int(os.environ.get("YOUTHINK_EMBEDDING_MAX_LENGTH", "512")))
        )
    except ValueError:
        embedding_max_length = 512
    try:
        embedding_batch_size = min(
            64, max(1, int(os.environ.get("YOUTHINK_EMBEDDING_BATCH_SIZE", "8")))
        )
    except ValueError:
        embedding_batch_size = 8

    # Priority: backend/static (copied build) -> frontend/dist (direct build)
    static_candidates = [
        backend_root / "static",
        backend_root.parent / "frontend" / "dist",
    ]
    static_dir = next((p for p in static_candidates if p.exists()), static_candidates[0])

    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "models").mkdir(parents=True, exist_ok=True)

    return AppConfig(
        data_dir=data_dir,
        host=host,
        port=port,
        static_dir=static_dir,
        embedding_max_length=embedding_max_length,
        embedding_batch_size=embedding_batch_size,
    )


_config_instance: AppConfig | None = None


def get_config() -> AppConfig:
    """Return cached AppConfig instance or initialize it."""
    global _config_instance
    if _config_instance is None:
        _config_instance = load_config()
    return _config_instance


def reset_config_for_testing(custom_data_dir: Path | None = None) -> AppConfig:
    """Reset cached configuration (used in unit tests)."""
    global _config_instance
    if custom_data_dir is not None:
        os.environ["YOUTHINK_DATA_DIR"] = str(custom_data_dir)
    _config_instance = load_config()
    return _config_instance
