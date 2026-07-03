@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT=hid_validation_capture.py"

where python >nul 2>nul
if errorlevel 1 goto try_py
set "PYTHON_CMD=python"
goto python_ready

:try_py
where py >nul 2>nul
if errorlevel 1 goto no_python
set "PYTHON_CMD=py -3"
goto python_ready

:no_python
echo [ERROR] Python not found. Please install Python 3 and add it to PATH.
pause
exit /b 1

:python_ready
echo ========================================
echo HID validation capture (host only)
echo Script: %SCRIPT%
echo Mode: host-only
echo ========================================

%PYTHON_CMD% "%SCRIPT%" --host-only

echo.
echo Capture finished. Check the newest folder under:
echo %~dp0captures
pause
exit /b %ERRORLEVEL%
