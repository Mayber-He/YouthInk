#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

MODE="${1:-dev}"
YOUTHINK_HOST="${YOUTHINK_HOST:-0.0.0.0}"
YOUTHINK_PORT="${YOUTHINK_PORT:-8000}"

PYTHON_BIN="python"
if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
fi

if [ "$MODE" = "--prod" ] || [ "$MODE" = "prod" ]; then
  echo "=============================================="
  echo "  YouthInk 青春小说工作台 · 生产模式启动"
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

  echo "[2/2] 正在启动 FastAPI 服务 (http://localhost:${YOUTHINK_PORT}) ..."
  export PYTHONPATH="$(pwd)/backend"
  exec "$PYTHON_BIN" -m uvicorn app.main:app --host "${YOUTHINK_HOST}" --port "${YOUTHINK_PORT}"
fi

# 默认进入前后端热更新开发模式
echo "=============================================================="
echo "  YouthInk 青春小说工作台 · 前后端热更新开发模式"
echo "=============================================================="

if [ ! -d "frontend/node_modules" ]; then
  echo "[准备] 正在安装前端依赖 (npm install)..."
  (cd frontend && npm install)
fi

echo "[1/2] 正在启动前端 Vite 热更新服务 (http://localhost:5173) ..."
(
  cd frontend
  exec npm run dev
) &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "正在停止服务..."
  kill "$FRONTEND_PID" 2>/dev/null || true
  wait "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "[2/2] 正在启动后端 FastAPI 热重载服务 (http://localhost:${YOUTHINK_PORT}) ..."
echo "--------------------------------------------------------------"
echo "  前端访问地址 (HMR 热更新): http://localhost:5173"
echo "  后端接口地址 (自动重载):   http://localhost:${YOUTHINK_PORT}"
echo "  接口文档 (Swagger UI):     http://localhost:${YOUTHINK_PORT}/docs"
echo "--------------------------------------------------------------"
echo "  提示: 前端开发服务器会自动代理 /api 到后端服务。"
echo "        请在浏览器访问: http://localhost:5173"
echo "        按 Ctrl+C 可同时停止前后端服务。"
echo "=============================================================="

export PYTHONPATH="$(pwd)/backend"
"$PYTHON_BIN" -m uvicorn app.main:app --reload --reload-dir "$(pwd)/backend" --host "${YOUTHINK_HOST}" --port "${YOUTHINK_PORT}"
