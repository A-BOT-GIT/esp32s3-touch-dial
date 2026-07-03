@echo off
setlocal
cd /d "%~dp0"

set "SCRIPT=hid_validation_capture.py"
set "PORT=%~1"
set "DURATION=%~2"

if "%DURATION%"=="" set "DURATION=20"

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
echo HID validation capture
echo Script: %SCRIPT%
echo Duration: %DURATION%s
if "%PORT%"=="" goto no_port_echo
echo Port: %PORT%
goto after_port_echo
:no_port_echo
echo Port: auto-detect
:after_port_echo
echo ========================================

if "%PORT%"=="" goto run_auto
%PYTHON_CMD% "%SCRIPT%" --port "%PORT%" --duration %DURATION%
goto done

:run_auto
%PYTHON_CMD% "%SCRIPT%" --duration %DURATION%

goto done

:done
echo.
echo Capture finished. Check the newest folder under:
echo %~dp0captures
pause
exit /b %ERRORLEVEL%
