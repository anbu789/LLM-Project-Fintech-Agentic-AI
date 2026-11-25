@echo off
setlocal enabledelayedexpansion

title FinTech Agent - Startup Orchestrator

echo ===============================================================================
echo            FinTech Agent - Windows Launch Orchestrator (INT450)
echo ===============================================================================
echo.

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

echo [*] Project Root: %PROJECT_ROOT%

:: 1. Verify Python Virtual Environment
set "PYTHON_EXE=%PROJECT_ROOT%.venv_clean\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment not found at: %PYTHON_EXE%
    echo Please ensure the .venv_clean virtual environment is installed.
    pause
    exit /b 1
)
echo [OK] Python runtime verified: %PYTHON_EXE%

:: 2. Verify Node.js and NPM
where npm >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] npm was not found in system PATH.
    echo Please install Node.js and npm to run the frontend application.
    pause
    exit /b 1
)
echo [OK] Node / npm runtime verified.

:: 3. Launch Backend API on port 8001 in separate window (scoped reload excludes tests & logs)
echo [*] Launching FastAPI Backend Server on http://127.0.0.1:8001 ...
start "FinTech Agent - Backend API" cmd.exe /k "cd /d "%PROJECT_ROOT%" && "%PYTHON_EXE%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001 --reload --reload-dir backend\app"

:: 4. Verify Backend is responding on port 8001 before reporting startup success
echo [*] Awaiting backend health verification on http://127.0.0.1:8001/health ...
set "BACKEND_READY=0"
for /L %%i in (1,1,30) do (
    if !BACKEND_READY! equ 0 (
        "%PYTHON_EXE%" -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2).getcode() == 200 else 1)" >nul 2>nul
        if !errorlevel! equ 0 (
            set "BACKEND_READY=1"
        ) else (
            timeout /t 1 /nobreak >nul
        )
    )
)

if !BACKEND_READY! equ 0 (
    echo [ERROR] Backend did not respond on http://127.0.0.1:8001/health within 30 seconds.
    echo Please check the "FinTech Agent - Backend API" window for startup details or exceptions.
    pause
    exit /b 1
) else (
    echo [OK] FinTech Agent backend verified and healthy on http://127.0.0.1:8001/health!
)

:: 5. Launch Execution Monitor in separate window (Terminal 2)
echo [*] Launching FinTech Agent Execution Monitor ...
start "FinTech Agent - Execution Monitor" cmd.exe /k "cd /d "%PROJECT_ROOT%" && "%PYTHON_EXE%" -m backend.app.monitor"

:: 6. Launch React Frontend in separate window (Terminal 3)
echo [*] Launching React Frontend Dev Server on http://localhost:5173 ...
start "FinTech Agent - Frontend UI" cmd.exe /k "cd /d "%PROJECT_ROOT%frontend" && npm.cmd run dev"

echo.
echo ===============================================================================
echo FinTech Agent Services Successfully Launched:
echo   - Backend API URL:          http://127.0.0.1:8001
echo   - Health Check:             http://127.0.0.1:8001/health
echo   - Interactive Swagger Docs: http://127.0.0.1:8001/docs
echo   - ReDoc Documentation:      http://127.0.0.1:8001/redoc
echo   - Frontend User Interface:  http://localhost:5173
echo.
echo Note: Live MongoDB execution is gated (PHASE6_LIVE_EXECUTION_ENABLED=False).
echo To launch background scheduler service, run start_scheduler.bat separately.
echo ===============================================================================
echo.
pause
