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

:: 3. Launch Backend API in separate window
echo [*] Launching FastAPI Backend Server on http://127.0.0.1:8000 ...
start "FinTech Agent - Backend API" cmd.exe /k "cd /d "%PROJECT_ROOT%" && "%PYTHON_EXE%" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload"

:: Brief delay before launching frontend
timeout /t 2 /nobreak >nul

:: 4. Launch React Frontend in separate window
echo [*] Launching React Frontend Dev Server on http://localhost:5173 ...
start "FinTech Agent - Frontend UI" cmd.exe /k "cd /d "%PROJECT_ROOT%frontend" && npm.cmd run dev"

echo.
echo ===============================================================================
echo FinTech Agent Services Successfully Launched:
echo   - Backend API URL:          http://127.0.0.1:8000
echo   - Interactive Swagger Docs: http://127.0.0.1:8000/docs
echo   - ReDoc Documentation:      http://127.0.0.1:8000/redoc
echo   - Frontend User Interface:  http://localhost:5173
echo.
echo Note: Live MongoDB execution is gated (PHASE6_LIVE_EXECUTION_ENABLED=False).
echo To launch background scheduler service, run start_scheduler.bat separately.
echo ===============================================================================
echo.
pause
