@echo off
setlocal

cd /d "%~dp0"

echo ==============================================
echo   YouthInk Workbench - Starting Server
echo ==============================================

if not exist "backend\static\index.html" (
    echo [1/2] Building frontend static assets...
    pushd "%~dp0frontend"
    if not exist "node_modules" call npm install
    call npm run build
    popd
) else (
    echo [1/2] Frontend static assets ready.
)

echo [2/2] Starting FastAPI on http://localhost:8000 ...
set "PYTHONPATH=%~dp0backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000