@echo off
setlocal
cd /d "%~dp0"

set "PS1=%~dp0capture_esp32_ble_hid_serial_v4.ps1"

if not exist "%PS1%" (
  echo [ERROR] Missing script:
  echo   %PS1%
  pause
  exit /b 1
)

echo ========================================
echo ESP32-S3 BLE HID Serial Capture
echo no-AddType v4
echo ========================================
echo.
echo Usage:
echo   run_serial_capture.bat
echo   run_serial_capture.bat COM6
echo   run_serial_capture.bat COM6 120
echo.
echo Notes:
echo   - No Python required.
echo   - Close Arduino Serial Monitor / PlatformIO monitor before running.
echo   - During capture: rotate left/right, press, long press.
echo.

set "PORT=%~1"
set "DURATION=%~2"

if "%DURATION%"=="" set "DURATION=60"

if "%PORT%"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -DurationSec %DURATION%
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Port "%PORT%" -DurationSec %DURATION%
)

set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
  echo [ERROR] Capture failed with exit code %ERR%.
) else (
  echo [OK] Capture finished.
)
echo.
pause
exit /b %ERR%
