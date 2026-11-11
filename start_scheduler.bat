@echo off
setlocal enabledelayedexpansion

title FinTech Agent - Background Scheduler Service

echo ===============================================================================
echo            FinTech Agent - Background Scheduler Service (Phase 7)
echo ===============================================================================
echo.

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

set "PYTHON_EXE=%PROJECT_ROOT%.venv_clean\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment not found at: %PYTHON_EXE%
    pause
    exit /b 1
)

echo [*] Preflight Safety Check: Verifying Phase 7 Scheduler Gate Configuration...
"%PYTHON_EXE%" -c "from backend.app.config import settings; import sys; sys.exit(0 if getattr(settings, 'PHASE7_SCHEDULER_ENABLED', False) else 2)"
set "GATE_STATUS=%errorlevel%"

if %GATE_STATUS% equ 2 (
    echo.
    echo [SAFETY NOTICE] The Background Scheduler Service is FAIL-CLOSED by default:
    echo   - PHASE7_SCHEDULER_ENABLED = False
    echo   - PHASE6_LIVE_EXECUTION_ENABLED = False
    echo.
    echo Rationale:
    echo   Autonomous recurring queries must not run unattended against live databases
    echo   until native MongoDB authentication and user authorization have been activated
    echo   and independently verified.
    echo.
    echo To enable the scheduler runner for testing or demonstration:
    echo   1. Verify your MongoDB auth and RBAC configuration.
    echo   2. Set PHASE7_SCHEDULER_ENABLED=True in .env or run with:
    echo      set PHASE7_SCHEDULER_ENABLED=True
    echo.
    echo The scheduler service will now safely exit without launching background jobs.
    echo ===============================================================================
    pause
    exit /b 0
)

echo [OK] Scheduler gate verified: PHASE7_SCHEDULER_ENABLED=True.
echo [*] Launching Single APScheduler Reconciliation Authority...
"%PYTHON_EXE%" -m backend.app.services.scheduler_runner
pause
