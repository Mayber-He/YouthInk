"""FastAPI application entry point, lifespan management, and StaticFiles SPA hosting."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1 import entities, memory, novels, outline, settings, stream, writing
from app.core.config import get_config
from app.core.exceptions import register_exception_handlers
from app.db.manager import ensure_global_db_initialized


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize global.db and data directories on startup."""
    ensure_global_db_initialized()
    yield


def create_app() -> FastAPI:
    """Create and configure the YouthInk FastAPI application."""
    app = FastAPI(
        title="YouthInk 青春小说工作台",
        version="0.1.0",
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    # API v1 routers
    app.include_router(settings.router, prefix="/api/v1")
    app.include_router(novels.router, prefix="/api/v1")
    app.include_router(entities.router, prefix="/api/v1")
    app.include_router(outline.router, prefix="/api/v1")
    app.include_router(writing.router, prefix="/api/v1")
    app.include_router(memory.router, prefix="/api/v1")
    app.include_router(stream.router, prefix="/api")

    @app.get("/api/health", tags=["system"])
    def health_check() -> dict[str, str]:
        cfg = get_config()
        return {
            "status": "ok",
            "version": "0.1.0",
            "data_dir": str(cfg.data_dir),
        }

    _mount_frontend_spa(app)
    return app


def _mount_frontend_spa(app: FastAPI) -> None:
    """Mount Vite frontend build artifacts if present, with SPA index.html fallback."""
    cfg = get_config()
    static_dir: Path = cfg.static_dir
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "ENDPOINT_NOT_FOUND",
                        "message": f"未找到接口: /{full_path}",
                        "detail": None,
                    }
                },
            )
        target_file = static_dir / full_path
        if full_path and target_file.exists() and target_file.is_file():
            return FileResponse(str(target_file))
        index_html = static_dir / "index.html"
        if index_html.exists():
            return FileResponse(str(index_html))
        return JSONResponse(
            status_code=200,
            content={
                "name": "YouthInk API Server",
                "message": "前端静态资源尚未构建，请运行前端开发服务器或执行 npm run build",
            },
        )


app = create_app()
