#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TOOLS_DIR="$ROOT_DIR/tools"
HOST_SCRIPT="$TOOLS_DIR/hid_validation_capture.py"
ANALYZE_SCRIPT="$TOOLS_DIR/analyze_hid_captures.py"
CAP_ROOT="$TOOLS_DIR/captures"
DEFAULT_BUILD_PATH="/tmp/esp32s3_touch_dial_ble_linux"
DEFAULT_FQBN="esp32:esp32:esp32s3"
DEFAULT_DURATION=20
DEFAULT_FLASH_METHOD="none"
DEFAULT_BAUD=115200
DEFAULT_COMMANDS=("HID STATUS" "ENC STATUS" "HID STATUS")

PORT=""
DURATION="$DEFAULT_DURATION"
FLASH_METHOD="$DEFAULT_FLASH_METHOD"
BUILD_PATH="$DEFAULT_BUILD_PATH"
FQBN="$DEFAULT_FQBN"
SKIP_BUILD=0
HOST_ONLY=0
BAUD="$DEFAULT_BAUD"

usage() {
  cat <<'EOF'
Linux BLE validation capture + analysis helper for esp32s3_touch_dial.

Usage:
  tools/run_ble_validation_and_analyze_linux.sh [options]

Options:
  --port <device>            Serial port, e.g. /dev/ttyACM0 (default: auto-detect)
  --duration <seconds>       Serial capture duration (default: 20)
  --baud <baud>              Serial baud rate (default: 115200)
  --flash-method <mode>      none | arduino | no-stub (default: none)
  --build-path <dir>         Fixed arduino-cli build path (default: /tmp/esp32s3_touch_dial_ble_linux)
  --fqbn <fqbn>              Build target (default: esp32:esp32:esp32s3)
  --skip-build               Skip compile step
  --host-only                Only collect host info + analyze; skip serial capture
  -h, --help                 Show this help

Examples:
  tools/run_ble_validation_and_analyze_linux.sh
  tools/run_ble_validation_and_analyze_linux.sh --port /dev/ttyACM0 --flash-method no-stub --duration 30
  tools/run_ble_validation_and_analyze_linux.sh --host-only
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
    echo "Install with: python3 -m pip install ${module}" >&2
    exit 1
  fi
}

find_esptool() {
  find "$HOME/.arduino15/packages/esp32/tools/esptool_py" -path '*/esptool.py' | sort | tail -n 1
}

find_boot_app0() {
  find "$HOME/.arduino15/packages/esp32/hardware/esp32" -path '*/tools/partitions/boot_app0.bin' | sort | tail -n 1
}

run_build() {
  echo "[1/4] Compile BLE target"
  rtk proxy arduino-cli compile --fqbn "$FQBN" --build-path "$BUILD_PATH" "$ROOT_DIR"
}

run_flash_arduino() {
  local actual_port="$1"
  echo "[2/4] Flash via arduino-cli upload on $actual_port"
  rtk proxy arduino-cli upload --fqbn "$FQBN" --port "$actual_port" "$ROOT_DIR"
}

run_flash_no_stub() {
  local actual_port="$1"
  local esptool
  local boot_app0
  esptool="$(find_esptool)"
  boot_app0="$(find_boot_app0)"

  if [[ -z "$esptool" || ! -f "$esptool" ]]; then
    echo "[ERROR] could not locate esptool.py under ~/.arduino15/packages/esp32/tools/esptool_py" >&2
    exit 1
  fi
  if [[ -z "$boot_app0" || ! -f "$boot_app0" ]]; then
    echo "[ERROR] could not locate boot_app0.bin under ~/.arduino15/packages/esp32/hardware/esp32" >&2
    exit 1
  fi

  local app_base="$BUILD_PATH/esp32s3_touch_dial.ino"
  local bootloader_bin="${app_base}.bootloader.bin"
  local partitions_bin="${app_base}.partitions.bin"
  local app_bin="${app_base}.bin"

  for f in "$bootloader_bin" "$partitions_bin" "$app_bin" "$boot_app0"; do
    if [[ ! -f "$f" ]]; then
      echo "[ERROR] required flash artifact missing: $f" >&2
      exit 1
    fi
  done

  echo "[2/4] Flash via esptool --no-stub on $actual_port"
  rtk proxy python3 "$esptool" \
    --chip esp32s3 \
    --port "$actual_port" \
    --baud 115200 \
    --before default_reset \
    --after hard_reset \
    --no-stub write_flash \
    --flash_mode dio \
    --flash_freq 80m \
    --flash_size 4MB \
    0x0 "$bootloader_bin" \
    0x8000 "$partitions_bin" \
    0xe000 "$boot_app0" \
    0x10000 "$app_bin"
}

run_capture_and_analysis() {
  local actual_port="$1"
  local ts host_dir full_dir
  ts="$(date +%Y%m%d_%H%M%S)"
  host_dir="$CAP_ROOT/ble_${ts}_host"
  full_dir="$CAP_ROOT/ble_${ts}_full"

  mkdir -p "$CAP_ROOT"

  echo "[3/4] Host-only capture -> $host_dir"
  python3 "$HOST_SCRIPT" --host-only --out-dir "$host_dir"

  if [[ "$HOST_ONLY" == "1" ]]; then
    echo "[4/4] Analyze host-only capture"
    python3 "$ANALYZE_SCRIPT" "$host_dir" --out-dir "$host_dir"
    echo "Done: $host_dir/analysis_report.txt"
    return 0
  fi

  echo "[4/4] Full BLE capture -> $full_dir"
  if [[ -n "$actual_port" ]]; then
    python3 "$HOST_SCRIPT" --port "$actual_port" --baud "$BAUD" --duration "$DURATION" --out-dir "$full_dir" --commands "${DEFAULT_COMMANDS[@]}"
  else
    python3 "$HOST_SCRIPT" --baud "$BAUD" --duration "$DURATION" --out-dir "$full_dir" --commands "${DEFAULT_COMMANDS[@]}"
  fi

  echo "[5/4] Analyze capture dirs"
  python3 "$ANALYZE_SCRIPT" "$host_dir" "$full_dir" --out-dir "$full_dir"
  echo "Done: $full_dir/analysis_report.txt"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="$2"; shift 2 ;;
    --duration)
      DURATION="$2"; shift 2 ;;
    --baud)
      BAUD="$2"; shift 2 ;;
    --flash-method)
      FLASH_METHOD="$2"; shift 2 ;;
    --build-path)
      BUILD_PATH="$2"; shift 2 ;;
    --fqbn)
      FQBN="$2"; shift 2 ;;
    --skip-build)
      SKIP_BUILD=1; shift ;;
    --host-only)
      HOST_ONLY=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "[ERROR] unknown arg: $1" >&2
      usage
      exit 1 ;;
  esac
done

if [[ "$FLASH_METHOD" != "none" && "$FLASH_METHOD" != "arduino" && "$FLASH_METHOD" != "no-stub" ]]; then
  echo "[ERROR] invalid --flash-method: $FLASH_METHOD" >&2
  exit 1
fi

require_cmd python3
require_cmd arduino-cli
require_python_module serial

cd "$ROOT_DIR"

echo "========================================"
echo "BLE validation capture and analysis (Linux)"
echo "Root dir: $ROOT_DIR"
echo "Port: ${PORT:-auto-detect}"
echo "Duration: ${DURATION}s"
echo "Build path: $BUILD_PATH"
echo "Flash method: $FLASH_METHOD"
echo "Host only: $HOST_ONLY"
echo "========================================"

if [[ "$SKIP_BUILD" != "1" ]]; then
  run_build
fi

ACTUAL_PORT="$PORT"
if [[ -z "$ACTUAL_PORT" && "$HOST_ONLY" != "1" ]]; then
  ACTUAL_PORT="$(python3 -c 'from tools.hid_validation_capture import autodetect_port; print(autodetect_port() or "")' 2>/dev/null || true)"
fi

if [[ "$FLASH_METHOD" == "arduino" ]]; then
  if [[ -z "$ACTUAL_PORT" ]]; then
    echo "[ERROR] no serial port found for arduino upload" >&2
    exit 1
  fi
  run_flash_arduino "$ACTUAL_PORT"
elif [[ "$FLASH_METHOD" == "no-stub" ]]; then
  if [[ -z "$ACTUAL_PORT" ]]; then
    echo "[ERROR] no serial port found for no-stub flash" >&2
    exit 1
  fi
  run_flash_no_stub "$ACTUAL_PORT"
fi

run_capture_and_analysis "$ACTUAL_PORT"
