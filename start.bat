@echo off
setlocal

cd /d "%~dp0"

echo ==============================================
echo   YouthInk Workbench - Starting Server
echo ==============================================

echo [1/2] Building frontend static assets...
pushd "%~dp0frontend"
if not exist "node_modules" call npm install
call npm run build
if errorlevel 1 (
    popd
    exit /b 1
)
popd

echo [2/2] Starting FastAPI on http://localhost:8000 ...
set "PYTHONPATH=%~dp0backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir "%~dp0backend"
