@echo off
setlocal
cd /d "%~dp0"

set "HOST_SCRIPT=hid_validation_capture.py"
set "ANALYZE_SCRIPT=analyze_hid_captures.py"
set "PORT=%~1"
set "DURATION=%~2"

if "%DURATION%"=="" set "DURATION=30"

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
echo Full HID capture and analysis
echo Duration: %DURATION%s
if "%PORT%"=="" goto no_port_echo
echo Port: %PORT%
goto after_port_echo
:no_port_echo
echo Port: auto-detect (not recommended if Bluetooth COM ports exist)
:after_port_echo
echo ========================================

echo [1/3] Host-only capture...
%PYTHON_CMD% "%HOST_SCRIPT%" --host-only
if errorlevel 1 goto failed

echo.
echo [2/3] Full capture...
if "%PORT%"=="" goto run_auto
%PYTHON_CMD% "%HOST_SCRIPT%" --port "%PORT%" --duration %DURATION%
goto analyze

:run_auto
%PYTHON_CMD% "%HOST_SCRIPT%" --duration %DURATION%

goto analyze

:analyze
echo.
echo [3/3] Analyze latest capture folders...
set "CAP1="
set "CAP2="
for /f "delims=" %%I in ('%PYTHON_CMD% -c "from pathlib import Path; p=Path(\"captures\"); dirs=sorted([d for d in p.iterdir() if d.is_dir()], key=lambda x: x.name); print(dirs[-2]); print(dirs[-1])"') do (
    if not defined CAP1 set "CAP1=%%I"
    if defined CAP1 if /i not "%%I"=="%CAP1%" set "CAP2=%%I"
)

if not defined CAP1 goto missing_caps
if not defined CAP2 goto missing_caps

echo Analyze dirs:
echo   %CAP1%
echo   %CAP2%
%PYTHON_CMD% "%ANALYZE_SCRIPT%" "%CAP1%" "%CAP2%"
if errorlevel 1 goto failed

echo.
echo Done. Check latest folders under:
echo %~dp0captures
pause
exit /b 0

:missing_caps
echo [ERROR] Could not find enough capture directories under captures\
pause
exit /b 1

:failed
echo.
echo [ERROR] Full capture and analysis failed.
pause
exit /b 1
