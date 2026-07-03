@echo off
setlocal
cd /d "%~dp0"

set "HOST_SCRIPT=hid_validation_capture.py"
set "ANALYZE_SCRIPT=analyze_hid_captures.py"
set "PORT=%~1"
set "DURATION=%~2"

if "%DURATION%"=="" set "DURATION=45"

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
%PYTHON_CMD% -c "import serial" >nul 2>nul
if errorlevel 1 goto no_pyserial

goto pyserial_ready

:no_pyserial
echo [ERROR] pyserial not installed.
echo Please run: pip install pyserial
echo Or: py -3 -m pip install pyserial
pause
exit /b 1

:pyserial_ready
for /f %%I in ('%PYTHON_CMD% -c "from datetime import datetime; print(datetime.now().strftime('%%Y%%m%%d_%%H%%M%%S'))"') do set "TS=%%I"
set "CAP_ROOT=%~dp0captures"
set "HOST_DIR=%CAP_ROOT%\ble_%TS%_host"
set "FULL_DIR=%CAP_ROOT%\ble_%TS%_full"

echo ========================================
echo BLE validation capture and analysis
echo Duration: %DURATION%s
echo Host dir: %HOST_DIR%
echo Full dir: %FULL_DIR%
if "%PORT%"=="" goto no_port_echo
echo Port: %PORT%
goto after_port_echo
:no_port_echo
echo Port: auto-detect (prefer native USB CDC of the board)
:after_port_echo
echo ========================================
echo.
echo During full capture, please do these on Windows:
echo   1. Open Bluetooth Settings / Add Device
ECHO   2. Find "ESP32-S3 Touch Dial"
echo   3. Pair / connect it
ECHO   4. Rotate left / rotate right / press on the device
ECHO   5. Disconnect and reconnect once if time allows
ECHO.
pause

echo [1/3] Host-only capture...
%PYTHON_CMD% "%HOST_SCRIPT%" --host-only --out-dir "%HOST_DIR%"
if errorlevel 1 goto failed

echo.
echo [2/3] Full BLE capture...
if "%PORT%"=="" goto run_auto
%PYTHON_CMD% "%HOST_SCRIPT%" --port "%PORT%" --duration %DURATION% --out-dir "%FULL_DIR%" --commands "HID STATUS" "ENC STATUS" "HID STATUS"
goto analyze

:run_auto
%PYTHON_CMD% "%HOST_SCRIPT%" --duration %DURATION% --out-dir "%FULL_DIR%" --commands "HID STATUS" "ENC STATUS" "HID STATUS"

goto analyze

:analyze
echo.
echo [3/3] Analyze capture dirs...
echo   %HOST_DIR%
echo   %FULL_DIR%
%PYTHON_CMD% "%ANALYZE_SCRIPT%" "%HOST_DIR%" "%FULL_DIR%" --out-dir "%FULL_DIR%"
if errorlevel 1 goto failed

echo.
echo Done. Check:
echo   %FULL_DIR%\analysis_report.txt
echo   %FULL_DIR%\analysis_report.json
echo   %FULL_DIR%\capture.log
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] BLE validation capture and analysis failed.
pause
exit /b 1
