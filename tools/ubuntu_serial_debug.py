#!/usr/bin/env python3
"""Ubuntu serial debug helper for ESP32-S3 Touch Dial.

It does not control system volume. It only keeps the wired protocol alive and
prints parsed events, so firmware/touch work can be verified on Ubuntu before
moving the PC listener to Windows.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass

try:
    import serial
    import serial.tools.list_ports
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit("pyserial is required: python3 -m pip install pyserial") from exc

RE_VOLUME = re.compile(r"^>VOLUME\s+(-?\d+)")
RE_TOUCH = re.compile(r"^>TOUCH\s+(.+)")


@dataclass
class Stats:
    started_at: float
    lines: int = 0
    volumes: int = 0
    touches: int = 0
    acks: int = 0


def autodetect_port() -> str | None:
    hints = ("USB", "ACM", "ESP32", "Espressif", "JTAG", "Serial")
    for port in serial.tools.list_ports.comports():
        desc = f"{port.device} {port.description or ''} {port.manufacturer or ''}"
        if any(h.lower() in desc.lower() for h in hints):
            return port.device
    return None


def handle_line(ser: serial.Serial, line: str, stats: Stats) -> None:
    stats.lines += 1

    if line.startswith(">HELLO") or line.startswith(">PING"):
        ser.write(b"ACK\n")
        stats.acks += 1
        print(f"[rx] {line}")
        print("[tx] ACK")
        return

    m = RE_VOLUME.match(line)
    if m:
        stats.volumes += 1
        value = max(0, min(100, int(m.group(1))))
        print(f"[volume] {value:3d}%")
        return

    m = RE_TOUCH.match(line)
    if m:
        stats.touches += 1
        print(f"[touch] {m.group(1)}")
        return

    if line.startswith(">PRESS"):
        print("[press] play/pause")
    elif line.startswith(">MUTE_TOGGLE"):
        print("[mute] toggle")
    elif line.startswith(">MODE"):
        print(f"[mode] {line}")
    elif line.startswith(">BOOT"):
        print(f"[boot] {line}")
    elif line.startswith(">I2C"):
        print(f"[i2c] {line}")
    else:
        print(f"[rx] {line}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default=None, help="Serial port, e.g. /dev/ttyACM0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, default=0, help="Stop after N seconds; 0 = run forever")
    args = parser.parse_args()

    port = args.port or autodetect_port()
    if not port:
        print("No serial port found. Pass --port /dev/ttyACM0", file=sys.stderr)
        return 2

    stats = Stats(started_at=time.time())
    print(f"Opening {port} @ {args.baud}")
    with serial.Serial(port, args.baud, timeout=0.2, write_timeout=1.0) as ser:
        deadline = None if args.seconds <= 0 else time.time() + args.seconds
        while deadline is None or time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip("\r\n\x00 ")
            if not line or not line.startswith(">"):
                continue
            handle_line(ser, line, stats)

    elapsed = max(0.001, time.time() - stats.started_at)
    print(
        f"Summary: lines={stats.lines} volumes={stats.volumes} touches={stats.touches} "
        f"acks={stats.acks} elapsed={elapsed:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
