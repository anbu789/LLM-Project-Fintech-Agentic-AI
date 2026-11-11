@echo off
setlocal enabledelayedexpansion

title FinTech Agent - Test & Verification Suite

echo ===============================================================================
echo            FinTech Agent - Full Regression Test Suite (INT450)
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

echo ===============================================================================
echo [STEP 1/3] Executing Backend Pytest Regression Suite...
echo ===============================================================================
"%PYTHON_EXE%" -m pytest backend/tests -v
if %errorlevel% neq 0 (
    echo.
    echo [FAILED] Backend pytest suite encountered errors.
    pause
    exit /b 1
)
echo.
echo [PASS] All Backend Pytest Tests Completed Successfully!
echo.

echo ===============================================================================
echo [STEP 2/3] Executing Frontend Vitest Suite...
echo ===============================================================================
cd /d "%PROJECT_ROOT%frontend"
call npm.cmd test -- --run
if %errorlevel% neq 0 (
    echo.
    echo [FAILED] Frontend vitest suite encountered errors.
    cd /d "%PROJECT_ROOT%"
    pause
    exit /b 1
)
echo.
echo [PASS] All Frontend Tests Completed Successfully!
echo.

echo ===============================================================================
echo [STEP 3/3] Executing Frontend Production Build...
echo ===============================================================================
call npm.cmd run build
if %errorlevel% neq 0 (
    echo.
    echo [FAILED] Frontend production build failed.
    cd /d "%PROJECT_ROOT%"
    pause
    exit /b 1
)
cd /d "%PROJECT_ROOT%"
echo.
echo [PASS] Frontend Production Build Verified!
echo.

echo ===============================================================================
echo [SUMMARY] ALL TEST SUITES PASSED (100%% SUCCESS):
echo   - Backend Unit, Security, Hardening and Integration Tests: PASS
echo   - Frontend Component and State Tests:                      PASS
echo   - Frontend Vite Production Build:                          PASS
echo ===============================================================================
echo.
pause
