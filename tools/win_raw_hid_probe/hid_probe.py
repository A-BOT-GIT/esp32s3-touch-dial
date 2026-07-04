#!/usr/bin/env python3
"""
ESP32-S3 Radial MVP — Windows Raw HID Probe

Usage:
  python hid_probe.py list
  python hid_probe.py listen [--vid 0x1234] [--pid 0x5678] [--timeout 120]
  python hid_probe.py listen --name "ESP32" [--timeout 120]

Requirements:
  pip install hidapi

This tool bypasses the Windows RadialController API and reads BLE HID
Input Reports directly from the HID device node.
"""

import sys
import time
import struct
import argparse
from datetime import datetime

try:
    import hid
except ImportError:
    print("ERROR: hidapi not installed.")
    print("  pip install hidapi")
    print("  (Windows may also need the hidapi DLL from https://github.com/libusb/hidapi/releases)")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Known ESP32 identifiers
# ---------------------------------------------------------------------------
ESP32_VIDS = [0x303A]  # Espressif

KNOWN_PATHS = [
    # BLE HID over GATT typically appears as:
    #   \\?\HID#{...}#{...}
    # or
    #   \\?\BTHLEDEVICE#{...}
]

SEARCH_KEYWORDS = [
    "ESP32", "Radial", "radial", "HID over GATT",
    "BTHLE", "Bluetooth HID", "HID-compliant",
]


# ---------------------------------------------------------------------------
# HID Report Parser
# ---------------------------------------------------------------------------
def parse_radial_payload(data: bytes) -> str:
    """Parse 2-byte Radial Controller payload.
    bit0         = button
    bit1..bit15  = signed 15-bit dial delta
    """
    if len(data) < 2:
        return f"({len(data)} bytes, too short for radial)"

    payload = struct.unpack("<H", data[:2])[0]
    button = payload & 0x01
    dial_raw = (payload >> 1) & 0x7FFF

    # Sign-extend 15-bit to Python int
    if dial_raw & 0x4000:
        dial_signed = dial_raw - 0x8000
    else:
        dial_signed = dial_raw

    return f"button={button} dial={dial_signed:+d}  (raw=0x{payload:04X})"


# ---------------------------------------------------------------------------
# Device Discovery
# ---------------------------------------------------------------------------
def list_devices():
    """Enumerate all HID devices, mark likely ESP32 candidates."""
    print("Enumerating HID devices...")
    print()

    candidates = []
    for d in hid.enumerate():
        vendor_id = d.get("vendor_id", 0)
        product_id = d.get("product_id", 0)
        path = d.get("path", b"").decode("utf-8", errors="replace") if isinstance(d.get("path"), bytes) else str(d.get("path", ""))
        mfg = d.get("manufacturer_string", "") or ""
        prod = d.get("product_string", "") or ""
        serial = d.get("serial_number", "") or ""
        usage_page = d.get("usage_page", 0)
        usage = d.get("usage", 0)

        combined = f"{mfg} {prod} {serial} {path}".lower()
        score = 0
        for kw in SEARCH_KEYWORDS:
            if kw.lower() in combined:
                score += 1
        if vendor_id in ESP32_VIDS:
            score += 5
        # Consumer Control or Generic Desktop usage pages
        if usage_page in (0x0001, 0x000C):
            score += 2

        info = {
            "score": score,
            "path": path,
            "vid": vendor_id,
            "pid": product_id,
            "mfg": mfg,
            "product": prod,
            "serial": serial,
            "usage_page": usage_page,
            "usage": usage,
        }
        candidates.append(info)

    # Sort by score descending
    candidates.sort(key=lambda x: -x["score"])

    if not candidates:
        print("No HID devices found.")
        return []

    print(f"{'Score':>5}  {'VID':>6}  {'PID':>6}  {'Usage':>10}  Product")
    print("-" * 70)
    for c in candidates:
        marker = " <--" if c["score"] >= 5 else ""
        us = f"0x{c['usage_page']:04X}:0x{c['usage']:04X}" if c["usage_page"] else ""
        print(f"{c['score']:>5}  0x{c['vid']:04X}  0x{c['pid']:04X}  {us:<10}  {c['product'][:40]}{marker}")
        if c["score"] >= 5:
            print(f"       path: {c['path']}")

    return candidates


# ---------------------------------------------------------------------------
# Live Report Listening
# ---------------------------------------------------------------------------
def listen_reports(path=None, vid=None, pid=None, name_filter=None, timeout=120):
    """Open a HID device and continuously read input reports."""
    # Find device
    target = None
    for d in hid.enumerate():
        d_path = d.get("path", b"").decode("utf-8", errors="replace") if isinstance(d.get("path"), bytes) else str(d.get("path", ""))
        d_vid = d.get("vendor_id", 0)
        d_pid = d.get("product_id", 0)
        d_prod = (d.get("product_string", "") or "").lower()
        d_mfg = (d.get("manufacturer_string", "") or "").lower()
        combined = f"{d_mfg} {d_prod} {d_path}".lower()

        if path and d_path == path:
            target = d
            break
        if vid is not None and pid is not None and d_vid == vid and d_pid == pid:
            target = d
            break
        if name_filter and (name_filter.lower() in combined):
            target = d
            break

    if target is None:
        print("ERROR: No matching HID device found.")
        print("Run 'python hid_probe.py list' to see available devices.")
        print("Then try: python hid_probe.py listen --path \"<device_path>\"")
        return

    d_path = target.get("path", b"").decode("utf-8", errors="replace") if isinstance(target.get("path"), bytes) else str(target.get("path", ""))
    d_vid = target.get("vendor_id", 0)
    d_pid = target.get("product_id", 0)
    d_prod = target.get("product_string", "") or ""

    print(f"Opening: VID=0x{d_vid:04X} PID=0x{d_pid:04X}  {d_prod}")
    print(f"Path:    {d_path}")
    print(f"Timeout: {timeout}s")
    print()
    print("Waiting for reports... (Ctrl+C to stop)")
    print()

    try:
        device = hid.Device(path=d_path)
    except Exception as e:
        print(f"ERROR: Cannot open device: {e}")
        print("Try running as Administrator, or close other HID tools.")
        return

    device.nonblocking = True

    deadline = time.time() + timeout
    count = 0

    try:
        while time.time() < deadline:
            data = device.read(64, timeout_ms=500)
            if data:
                count += 1
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                hex_str = " ".join(f"{b:02X}" for b in data)
                parsed = parse_radial_payload(bytes(data)) if len(data) >= 2 else ""
                print(f"[{ts}] #{count:04d} len={len(data)}  {hex_str}")
                if parsed:
                    print(f"               {parsed}")
                sys.stdout.flush()
            else:
                time.sleep(0.01)
    except KeyboardInterrupt:
        print()
        print("Stopped by user.")
    finally:
        device.close()

    print(f"Total reports received: {count}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="ESP32-S3 Radial MVP Raw HID Probe")
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List HID devices")

    p_listen = sub.add_parser("listen", help="Listen for input reports")
    p_listen.add_argument("--path", help="Device path (e.g. \\\\?\\HID#...)")
    p_listen.add_argument("--vid", type=lambda x: int(x, 16), help="Vendor ID (hex)")
    p_listen.add_argument("--pid", type=lambda x: int(x, 16), help="Product ID (hex)")
    p_listen.add_argument("--name", help="Filter by product name substring")
    p_listen.add_argument("--timeout", type=int, default=120, help="Seconds to listen (default 120)")

    args = parser.parse_args()

    if args.command == "list":
        list_devices()
    elif args.command == "listen":
        listen_reports(
            path=args.path,
            vid=args.vid,
            pid=args.pid,
            name_filter=args.name,
            timeout=args.timeout,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
