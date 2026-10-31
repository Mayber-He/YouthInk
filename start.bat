@echo off
setlocal

cd /d "%~dp0"

if not defined YOUTHINK_HOST set "YOUTHINK_HOST=0.0.0.0"
if not defined YOUTHINK_PORT set "YOUTHINK_PORT=8000"

if /i "%~1"=="--prod" goto :prod_mode
if /i "%~1"=="prod" goto :prod_mode

:dev_mode
echo ==============================================================
echo   YouthInk Workbench - Dev Mode (Hot Reload)
echo ==============================================================

if not exist "frontend\node_modules" (
    echo [Prep] Installing frontend dependencies...
    pushd "%~dp0frontend"
    call npm install
    popd
)

echo [1/2] Starting Frontend Vite Dev Server (Hot Reload)...
pushd "%~dp0frontend"
start "YouthInk-Frontend-Dev" cmd /c "npm run dev"
popd

echo [2/2] Starting Backend FastAPI Server (Auto Reload)...
echo --------------------------------------------------------------
echo   Frontend (HMR):     http://localhost:5173
echo   Backend API:        http://localhost:%YOUTHINK_PORT%
echo   API Docs (Swagger): http://localhost:%YOUTHINK_PORT%/docs
echo --------------------------------------------------------------
echo   Tip: Open http://localhost:5173 in your browser.
echo        Press Ctrl+C in this window to stop server.
echo ==============================================================

set "PYTHONPATH=%~dp0backend"
python -m uvicorn app.main:app --reload --reload-dir "%~dp0backend" --host %YOUTHINK_HOST% --port %YOUTHINK_PORT%

taskkill /FI "WINDOWTITLE eq YouthInk-Frontend-Dev*" /T /F >nul 2>&1
goto :eof

:prod_mode
echo ==============================================================
echo   YouthInk Workbench - Production Mode
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

echo [2/2] Starting FastAPI on http://localhost:%YOUTHINK_PORT% ...
set "PYTHONPATH=%~dp0backend"
python -m uvicorn app.main:app --host %YOUTHINK_HOST% --port %YOUTHINK_PORT%
goto :eof
