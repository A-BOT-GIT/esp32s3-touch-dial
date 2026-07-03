#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None


def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_run(command: list[str] | str, *, shell: bool = False, timeout: int = 20) -> dict:
    try:
        proc = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": command,
        }
    except Exception as exc:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": repr(exc),
            "command": command,
        }


class Recorder:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = out_dir / "capture.log"
        self.json_path = out_dir / "summary.json"
        self.summary: dict = {
            "started_at": now_ts(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python": sys.version,
            },
            "host_commands": {},
            "serial_ports": [],
            "serial_session": {
                "port": None,
                "baud": None,
                "opened": False,
                "commands_sent": [],
                "lines": [],
                "stats": {"hello": 0, "ping": 0, "hid_ready": 0, "usb_started": 0},
            },
        }

    def log(self, message: str) -> None:
        line = f"[{now_ts()}] {message}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def save_json(self) -> None:
        self.summary["finished_at"] = now_ts()
        self.json_path.write_text(json.dumps(self.summary, ensure_ascii=False, indent=2), encoding="utf-8")


def list_serial_ports() -> list[dict]:
    if serial is None:
        return []
    rows = []
    for p in serial.tools.list_ports.comports():
        rows.append(
            {
                "device": p.device,
                "description": p.description,
                "manufacturer": p.manufacturer,
                "product": getattr(p, "product", None),
                "vid": getattr(p, "vid", None),
                "pid": getattr(p, "pid", None),
                "serial_number": getattr(p, "serial_number", None),
                "location": getattr(p, "location", None),
                "hwid": p.hwid,
            }
        )
    return rows


def port_identity_score(row: dict) -> int:
    text = " ".join(
        str(row.get(k) or "")
        for k in ["device", "description", "manufacturer", "product", "hwid", "serial_number"]
    ).lower()
    vid = row.get("vid")
    pid = row.get("pid")

    score = 0

    # 最优先：ESP32-S3 native USB CDC / JTAG+CDC 口。COM 号会变，但 303A:1001 身份稳定。
    if vid == 0x303A and pid == 0x1001:
        score += 100
    if "303a:1001" in text or "vid:pid=303a:1001" in text or "vid_303a&pid_1001" in text:
        score += 100

    # 次优先：明确的 Espressif/native USB 线索。
    if "espressif" in text:
        score += 30
    if "usb jtag/serial" in text or "usb jtag/serial debug unit" in text:
        score += 30
    if "esp32" in text or "esp32-s3" in text:
        score += 20
    if "acm" in text:
        score += 10

    # 回退：桥口/常见 USB UART 芯片，只在没有 native USB 时选。
    if vid == 0x1A86 and pid == 0x55D3:
        score += 20
    if vid == 0x10C4:
        score += 15
    if any(key in text for key in ["ch343", "wch", "usb-enhanced-serial", "cp210", "ftdi", "usb-serial"]):
        score += 10

    # 最弱兜底：泛 USB/串口口，但不该压过明确身份口。
    if any(key in text for key in ["usb serial device", "serial", "usb"]):
        score += 1

    return score


def autodetect_port() -> str | None:
    best_row = None
    best_score = 0
    for row in list_serial_ports():
        score = port_identity_score(row)
        if score > best_score:
            best_row = row
            best_score = score
    if best_row is None:
        return None
    return best_row.get("device")


def collect_host_info(rec: Recorder) -> None:
    system = platform.system().lower()

    commands: list[tuple[str, list[str] | str, bool]] = []
    if system == "windows":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if ps:
            commands.extend(
                [
                    (
                        "pnp_usb",
                        [ps, "-NoProfile", "-Command", "Get-PnpDevice -PresentOnly | Where-Object {$_.Class -in 'USB','Ports','HIDClass'} | Sort-Object Class,FriendlyName | Format-Table -AutoSize Class,Status,FriendlyName,InstanceId"],
                        False,
                    ),
                    (
                        "cim_pnp",
                        [ps, "-NoProfile", "-Command", "Get-CimInstance Win32_PnPEntity | Where-Object {$_.Name -match 'ESP32|HID|USB|Serial|Dial|JTAG|COM'} | Sort-Object Name | Select-Object Name,PNPClass,DeviceID,Manufacturer,Status | Format-List"],
                        False,
                    ),
                    (
                        "usb_controllers",
                        [ps, "-NoProfile", "-Command", "Get-CimInstance Win32_USBControllerDevice | Select-Object -First 80 | Format-List"],
                        False,
                    ),
                ]
            )
    else:
        commands.extend(
            [
                ("uname", ["uname", "-a"], False),
                ("lsusb", ["lsusb"], False),
                ("usb_devices", ["bash", "-lc", "for d in /sys/bus/usb/devices/*; do [ -f \"$d/idVendor\" ] || continue; echo \"== $(basename \"$d\") ==\"; paste -d' ' <(echo vendor:) \"$d/idVendor\"; paste -d' ' <(echo product:) \"$d/idProduct\"; [ -f \"$d/manufacturer\" ] && paste -d' ' <(echo manufacturer:) \"$d/manufacturer\"; [ -f \"$d/product\" ] && paste -d' ' <(echo product_name:) \"$d/product\"; done"], False),
            ]
        )

    for name, cmd, shell in commands:
        result = safe_run(cmd, shell=shell)
        rec.summary["host_commands"][name] = result
        status = "ok" if result["ok"] else f"fail rc={result['returncode']}"
        rec.log(f"host command {name}: {status}")
        txt_path = rec.out_dir / f"host_{name}.txt"
        txt_path.write_text(
            f"COMMAND: {result['command']}\nRETURN CODE: {result['returncode']}\n\nSTDOUT:\n{result['stdout']}\n\nSTDERR:\n{result['stderr']}\n",
            encoding="utf-8",
        )


def parse_line_stats(rec: Recorder, line: str) -> None:
    stats = rec.summary["serial_session"]["stats"]
    if line.startswith(">HELLO"):
        stats["hello"] += 1
    if line.startswith(">PING"):
        stats["ping"] += 1
    if ">HID ready" in line:
        stats["hid_ready"] += 1
    if ">USB started" in line:
        stats["usb_started"] += 1


def serial_capture(rec: Recorder, port: str | None, baud: int, duration: float, commands: list[str]) -> None:
    rec.summary["serial_ports"] = list_serial_ports()
    ports_txt = rec.out_dir / "serial_ports.json"
    ports_txt.write_text(json.dumps(rec.summary["serial_ports"], ensure_ascii=False, indent=2), encoding="utf-8")

    if serial is None:
        rec.log("pyserial 未安装，跳过串口抓取")
        return

    chosen = port or autodetect_port()
    rec.summary["serial_session"]["port"] = chosen
    rec.summary["serial_session"]["baud"] = baud

    if not chosen:
        rec.log("未找到串口，跳过串口抓取")
        return

    rec.log(f"opening serial port {chosen} @ {baud}")
    try:
        with serial.Serial(chosen, baud, timeout=0.2, write_timeout=1.0) as ser:
            # ESP32-S3 TinyUSB CDC on this board requires DTR asserted before it starts speaking.
            # Keep RTS low to avoid reset/bootloader side effects while capturing evidence.
            ser.dtr = True
            ser.rts = False
            rec.log(f"serial control lines: DTR={ser.dtr} RTS={ser.rts}")
            rec.summary["serial_session"]["opened"] = True
            start = time.time()
            command_index = 0
            next_send = start + 2.0
            while time.time() - start < duration:
                now = time.time()
                if command_index < len(commands) and now >= next_send:
                    cmd = commands[command_index].rstrip("\r\n")
                    ser.write((cmd + "\n").encode("utf-8"))
                    rec.summary["serial_session"]["commands_sent"].append({"ts": now_ts(), "command": cmd})
                    rec.log(f"[tx] {cmd}")
                    command_index += 1
                    next_send = now + 0.5

                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip("\r\n\x00 ")
                if not line:
                    continue
                rec.summary["serial_session"]["lines"].append({"ts": now_ts(), "line": line})
                parse_line_stats(rec, line)
                rec.log(f"[rx] {line}")

                if line.startswith(">HELLO") or line.startswith(">PING"):
                    ser.write(b"ACK\n")
                    rec.log("[tx] ACK")
    except Exception as exc:
        rec.log(f"serial capture failed: {exc!r}")
        rec.summary["serial_session"]["error"] = repr(exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture HID/USB/serial validation evidence for ESP32-S3 touch dial")
    parser.add_argument("--port", default=None, help="Serial port, e.g. COM7 or /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--duration", type=float, default=15.0, help="Serial capture duration in seconds")
    parser.add_argument("--out-dir", default=None, help="Output directory; default: tools/captures/<timestamp>")
    parser.add_argument(
        "--commands",
        nargs="*",
        default=["HID STATUS", "USB STATUS", "ENC STATUS", "ENC RIGHT", "ENC PRESS"],
        help="Commands to send over serial after boot",
    )
    parser.add_argument("--host-only", action="store_true", help="Only collect host enumeration info; skip serial")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = Path(__file__).resolve().parent / "captures" / timestamp
    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else default_out
    rec = Recorder(out_dir)
    rec.log(f"output directory: {out_dir}")
    collect_host_info(rec)
    if not args.host_only:
        serial_capture(rec, args.port, args.baud, args.duration, args.commands)
    rec.save_json()
    rec.log(f"capture complete: {rec.log_path}")
    rec.log(f"summary json: {rec.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
