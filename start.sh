#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=============================================="
echo "  YouthInk 青春小说工作台 · 一键启动脚本"
echo "=============================================="

if [ ! -f "backend/static/index.html" ]; then
  echo "[1/2] 正在构建前端静态资源..."
  (
    cd frontend
    if [ ! -d "node_modules" ]; then
      npm install
    fi
    npm run build
  )
else
  echo "[1/2] 已检测到前端静态产物 backend/static/index.html"
fi

echo "[2/2] 正在启动 FastAPI 服务 (http://localhost:8000) ..."
export PYTHONPATH="$(pwd)/backend"
exec python -m uvicorn app.main:app --host "${YOUTHINK_HOST:-0.0.0.0}" --port "${YOUTHINK_PORT:-8000}"
