#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_PATH="/tmp/esp32s3_touch_dial_deploy"
FQBN="esp32:esp32:esp32s3:USBMode=hwcdc,CDCOnBoot=cdc"
FLASH_PORT="/dev/ttyACM0"
CONTROL_PORT="/dev/ttyACM1"
FLASH_BAUD="115200"
CONTROL_BAUD="115200"
START_WAIT="15"
PROBE_WAIT="1.5"
CONTROL_READY_TIMEOUT="30"
FLASH_METHOD="full"
START_METHOD="dtr"
START_FALLBACK="watchdog"
ERASE_FIRST="0"
SKIP_COMPILE="0"
SKIP_FLASH="0"
SKIP_START="0"
SKIP_PROBE="0"
PROBE_COMMANDS=("LOG QUIET" "BLE STATUS" "HID STATUS")

usage() {
  cat <<'EOF'
Linux deploy helper for esp32s3_touch_dial.

Purpose:
  Compile the sketch, flash the board from Linux, start the firmware, and probe
  the serial control channel. Windows-side BLE/HID validation is intentionally
  left manual.

Usage:
  tools/deploy_linux.sh [options]

Options:
  --build-path <dir>         arduino-cli build path
  --fqbn <fqbn>              compile target
  --flash-port <device>      flash port (default: /dev/ttyACM0)
  --control-port <device>    control/log port (default: /dev/ttyACM1)
  --flash-baud <baud>        flash baud (default: 115200)
  --control-baud <baud>      control baud (default: 115200)
  --flash-method <mode>      full | arduino (default: full)
  --start-method <mode>      dtr | none (default: dtr)
  --start-fallback <mode>    watchdog | none (default: watchdog)
  --start-wait <seconds>     wait after start pulse (default: 15)
  --probe-wait <seconds>     wait after each probe command (default: 1.5)
  --control-ready-timeout <seconds>
                             wait for /dev/ttyACM1 to reappear before probe
                             (default: 30)
  --erase-first              erase flash before write_flash
  --skip-compile             skip arduino-cli compile
  --skip-flash               skip flashing
  --skip-start               skip startup action
  --skip-probe               skip serial probe after startup
  -h, --help                 show help

Examples:
  tools/deploy_linux.sh
  tools/deploy_linux.sh --erase-first
  tools/deploy_linux.sh --skip-flash --skip-start
  tools/deploy_linux.sh --flash-method arduino

Notes:
  - full mode flashes bootloader + partitions + boot_app0 + app0 + app1.
  - full mode assumes the board is already in ROM bootloader if your hardware
    cannot auto-enter bootloader from Linux.
  - start uses the CH343P DTR pulse on /dev/ttyACM1.
  - if DTR start produces no control-channel response, the script can fall back
    to esptool 5.3.1 watchdog reset on /dev/ttyACM0.
EOF
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[ERROR] missing command: $cmd" >&2
    exit 1
  fi
}

require_python_module() {
  local module="$1"
  if ! python3 -c "import ${module}" >/dev/null 2>&1; then
    echo "[ERROR] missing python module: ${module}" >&2
    echo "Install with: python3 -m pip install --user ${module}" >&2
    exit 1
  fi
}

find_core_esptool() {
  find "$HOME/.arduino15/packages/esp32/tools/esptool_py" -path '*/esptool.py' | sort | tail -n 1
}

find_boot_app0() {
  find "$HOME/.arduino15/packages/esp32/hardware/esp32" -path '*/tools/partitions/boot_app0.bin' | sort | tail -n 1
}

find_user_esptool() {
  if command -v esptool >/dev/null 2>&1; then
    command -v esptool
    return 0
  fi
  if [[ -x "$HOME/.local/bin/esptool.py" ]]; then
    printf '%s\n' "$HOME/.local/bin/esptool.py"
    return 0
  fi
  return 1
}

artifact_base() {
  printf '%s/esp32s3_touch_dial.ino' "$BUILD_PATH"
}

run_compile() {
  echo "[1/4] Compile"
  arduino-cli compile --fqbn "$FQBN" --build-path "$BUILD_PATH" "$ROOT_DIR"
}

run_flash_arduino() {
  echo "[2/4] Flash via arduino-cli upload on $FLASH_PORT"
  arduino-cli upload --fqbn "$FQBN" --port "$FLASH_PORT" "$ROOT_DIR"
}

run_flash_full() {
  local esptool boot_app0 base bootloader_bin partitions_bin app_bin
  esptool="$(find_core_esptool)"
  boot_app0="$(find_boot_app0)"
  base="$(artifact_base)"
  bootloader_bin="${base}.bootloader.bin"
  partitions_bin="${base}.partitions.bin"
  app_bin="${base}.bin"

  if [[ -z "$esptool" || ! -f "$esptool" ]]; then
    echo "[ERROR] core esptool.py not found under ~/.arduino15/packages/esp32/tools/esptool_py" >&2
    exit 1
  fi
  if [[ -z "$boot_app0" || ! -f "$boot_app0" ]]; then
    echo "[ERROR] boot_app0.bin not found under ~/.arduino15/packages/esp32/hardware/esp32" >&2
    exit 1
  fi

  for f in "$bootloader_bin" "$partitions_bin" "$app_bin" "$boot_app0"; do
    if [[ ! -f "$f" ]]; then
      echo "[ERROR] required artifact missing: $f" >&2
      exit 1
    fi
  done

  if [[ "$ERASE_FIRST" == "1" ]]; then
    echo "[2/4] Erase flash on $FLASH_PORT"
    python3 "$esptool" --chip esp32s3 --port "$FLASH_PORT" --baud 921600 erase_flash
  fi

  echo "[2/4] Full flash on $FLASH_PORT"
  python3 "$esptool" \
    --chip esp32s3 \
    --port "$FLASH_PORT" \
    --baud "$FLASH_BAUD" \
    --before default_reset \
    --after no_reset \
    --no-stub write_flash \
    --flash_mode dio \
    --flash_freq 80m \
    --flash_size 4MB \
    0x0 "$bootloader_bin" \
    0x8000 "$partitions_bin" \
    0xe000 "$boot_app0" \
    0x10000 "$app_bin" \
    0x150000 "$app_bin"
}

run_start_dtr() {
  echo "[3/4] Start firmware via CH343P DTR pulse on $CONTROL_PORT"
  python3 - "$CONTROL_PORT" "$CONTROL_BAUD" "$START_WAIT" <<'PY'
import sys
import time
import serial

port = sys.argv[1]
baud = int(sys.argv[2])
wait_s = float(sys.argv[3])

s = serial.Serial(port, baud, timeout=2, dsrdtr=False)
try:
    s.rts = True
    s.dtr = True
    time.sleep(0.3)
    s.dtr = False
    time.sleep(0.5)
    s.dtr = True
    time.sleep(0.5)
finally:
    s.close()

print(f"[START] DTR pulse done, waiting {wait_s:.1f}s for firmware boot")
time.sleep(wait_s)
PY
}

run_start_watchdog_reset() {
  local esptool
  esptool="$(find_user_esptool || true)"
  if [[ -z "$esptool" ]]; then
    echo "[ERROR] esptool 5.x not found for watchdog reset fallback" >&2
    return 1
  fi
  echo "[3b/4] Fallback start via watchdog reset on $FLASH_PORT"
  "$esptool" --chip esp32s3 --port "$FLASH_PORT" --baud "$FLASH_BAUD" --after watchdog-reset chip-id
}

wait_for_control_port() {
  local label="${1:-[WAIT] Waiting for control port $CONTROL_PORT}"
  echo "$label"
  python3 - "$CONTROL_PORT" "$CONTROL_READY_TIMEOUT" <<'PY'
import glob
import os
import sys
import time

port = sys.argv[1]
timeout_s = float(sys.argv[2])
deadline = time.time() + timeout_s

while time.time() < deadline:
    if os.path.exists(port):
        print(f"[WAIT] control port ready: {port}")
        raise SystemExit(0)
    ports = " ".join(sorted(glob.glob("/dev/ttyACM*"))) or "(none)"
    print(f"[WAIT] control port missing: {port} visible={ports}")
    time.sleep(1.0)

print(f"[WAIT] timeout after {timeout_s:.1f}s waiting for {port}", file=sys.stderr)
raise SystemExit(1)
PY
}

run_probe() {
  local label="${1:-[4/4] Probe control channel on $CONTROL_PORT}"
  echo "$label"
  python3 - "$CONTROL_PORT" "$CONTROL_BAUD" "$PROBE_WAIT" "${PROBE_COMMANDS[@]}" <<'PY'
import sys
import time
import serial

port = sys.argv[1]
baud = int(sys.argv[2])
probe_wait = float(sys.argv[3])
commands = sys.argv[4:]

s = serial.Serial(port, baud, timeout=1, dsrdtr=False)
had_response = False
try:
    s.rts = True
    s.dtr = True
    time.sleep(0.3)

    def read_chunk(wait_s: float) -> str:
        time.sleep(wait_s)
        data = bytearray()
        while s.in_waiting > 0:
            data.extend(s.read(s.in_waiting))
            time.sleep(0.05)
        return data.decode("latin-1", errors="replace").replace("\r", "")

    _ = read_chunk(0.2)
    for cmd in commands:
        s.write((cmd + "\r\n").encode())
        out = read_chunk(probe_wait)
        print(f"[PROBE] >>> {cmd}")
        if out.strip():
            had_response = True
            print(out.rstrip())
        else:
            print("[PROBE] (no response)")
finally:
    s.close()
raise SystemExit(0 if had_response else 2)
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-path)
      BUILD_PATH="$2"; shift 2 ;;
    --fqbn)
      FQBN="$2"; shift 2 ;;
    --flash-port)
      FLASH_PORT="$2"; shift 2 ;;
    --control-port)
      CONTROL_PORT="$2"; shift 2 ;;
    --flash-baud)
      FLASH_BAUD="$2"; shift 2 ;;
    --control-baud)
      CONTROL_BAUD="$2"; shift 2 ;;
    --flash-method)
      FLASH_METHOD="$2"; shift 2 ;;
    --start-method)
      START_METHOD="$2"; shift 2 ;;
    --start-fallback)
      START_FALLBACK="$2"; shift 2 ;;
    --start-wait)
      START_WAIT="$2"; shift 2 ;;
    --probe-wait)
      PROBE_WAIT="$2"; shift 2 ;;
    --control-ready-timeout)
      CONTROL_READY_TIMEOUT="$2"; shift 2 ;;
    --erase-first)
      ERASE_FIRST="1"; shift ;;
    --skip-compile)
      SKIP_COMPILE="1"; shift ;;
    --skip-flash)
      SKIP_FLASH="1"; shift ;;
    --skip-start)
      SKIP_START="1"; shift ;;
    --skip-probe)
      SKIP_PROBE="1"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "[ERROR] unknown arg: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ "$FLASH_METHOD" != "full" && "$FLASH_METHOD" != "arduino" ]]; then
  echo "[ERROR] invalid --flash-method: $FLASH_METHOD" >&2
  exit 1
fi
if [[ "$START_METHOD" != "dtr" && "$START_METHOD" != "none" ]]; then
  echo "[ERROR] invalid --start-method: $START_METHOD" >&2
  exit 1
fi
if [[ "$START_FALLBACK" != "watchdog" && "$START_FALLBACK" != "none" ]]; then
  echo "[ERROR] invalid --start-fallback: $START_FALLBACK" >&2
  exit 1
fi

require_cmd python3
require_cmd arduino-cli
require_python_module serial

cd "$ROOT_DIR"

echo "========================================"
echo "Linux deploy helper"
echo "Root dir: $ROOT_DIR"
echo "FQBN: $FQBN"
echo "Build path: $BUILD_PATH"
echo "Flash port: $FLASH_PORT"
echo "Control port: $CONTROL_PORT"
echo "Flash method: $FLASH_METHOD"
echo "Start method: $START_METHOD"
echo "Start fallback: $START_FALLBACK"
echo "Control ready timeout: $CONTROL_READY_TIMEOUT"
echo "Erase first: $ERASE_FIRST"
echo "========================================"

if [[ "$SKIP_COMPILE" != "1" ]]; then
  run_compile
fi

if [[ "$SKIP_FLASH" != "1" ]]; then
  if [[ "$FLASH_METHOD" == "arduino" ]]; then
    run_flash_arduino
  else
    run_flash_full
  fi
fi

if [[ "$SKIP_START" != "1" && "$START_METHOD" == "dtr" ]]; then
  run_start_dtr
fi

if [[ "$SKIP_PROBE" != "1" ]]; then
  wait_for_control_port "[4-pre] Wait for control channel on $CONTROL_PORT"
  if ! run_probe; then
    if [[ "$SKIP_START" != "1" && "$START_FALLBACK" == "watchdog" ]]; then
      run_start_watchdog_reset
      wait_for_control_port "[4b-pre] Wait for control channel after watchdog reset"
      run_probe "[4b/4] Re-probe control channel after watchdog reset"
    else
      exit 2
    fi
  fi
fi

echo "[DONE] Linux-side deploy flow finished."
