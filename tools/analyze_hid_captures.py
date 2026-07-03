#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

BOARD_BRIDGE_VIDPID = "VID_1A86&PID_55D3"
NATIVE_USB_HINTS = [
    "ESP32",
    "ESP32-S3",
    "ESPRESSIF",
    "VID_303A",
    "TOUCH DIAL",
    "DIAL",
    "PRODUCT=ESP32-S3 TOUCH DIAL",
]
EXCLUDE_HINTS = [
    "BTHENUM",
    "BLUETOOTH",
    "GVINPUT",
    "LOGITECH",
    "APPLE",
    "INTEL(R) HID EVENT FILTER",
]


@dataclass
class CaptureAnalysis:
    capture_dir: str
    started_at: str | None
    finished_at: str | None
    selected_port: str | None
    expected_board_port: str | None
    preferred_port: str | None
    preferred_port_kind: str | None
    selected_port_matches_preferred: bool | None
    serial_opened: bool
    serial_error: str | None
    hello_count: int
    ping_count: int
    hid_ready_count: int
    usb_started_count: int
    hid_status_lines: list[str]
    usb_mode: str | None
    control_channel: str | None
    hid_supported: bool | None
    board_bridge_present: bool
    board_bridge_instance_ids: list[str]
    native_usb_ports: list[str]
    native_usb_candidates: list[str]
    likely_native_usb_enumerated: bool
    conclusions: list[str]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def parse_capture_log(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {
        "selected_port": None,
        "hello_count": 0,
        "ping_count": 0,
        "hid_ready_count": 0,
        "usb_started_count": 0,
        "hid_status_lines": [],
        "serial_error": None,
    }
    m = re.search(r"opening serial port\s+(\S+)\s+@", text, flags=re.I)
    if m:
        data["selected_port"] = m.group(1)

    data["hello_count"] = len(re.findall(r"\[rx\]\s+>HELLO\b", text))
    data["ping_count"] = len(re.findall(r"\[rx\]\s+>PING\b", text))
    data["hid_ready_count"] = len(re.findall(r">HID ready\b", text))
    data["usb_started_count"] = len(re.findall(r">USB started\b", text))
    data["hid_status_lines"] = re.findall(r".*>HID_STATUS.*", text)

    m = re.search(r"serial capture failed:\s*(.+)", text)
    if m:
        data["serial_error"] = m.group(1).strip()
    return data


def extract_instance_ids(host_text: str) -> list[str]:
    ids: list[str] = []
    for line in host_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "USB\\VID_" in line or "HID\\VID_" in line or "BTHENUM\\" in line:
            ids.extend(re.findall(r"((?:USB|HID|BTHENUM)\\[^\s]+)", line))
    out = []
    seen = set()
    for item in ids:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def find_native_candidates(host_text: str) -> list[str]:
    candidates: list[str] = []
    for raw in host_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("COMMAND:") or line.startswith("RETURN CODE:") or line.startswith("STDOUT:") or line.startswith("STDERR:"):
            continue
        upper = line.upper()
        if any(h in upper for h in NATIVE_USB_HINTS) and not any(bad in upper for bad in EXCLUDE_HINTS):
            candidates.append(line)
    dedup: list[str] = []
    seen = set()
    for line in candidates:
        if line not in seen:
            seen.add(line)
            dedup.append(line)
    return dedup


def pick_board_port(summary: dict[str, Any]) -> tuple[str | None, list[str]]:
    ports = summary.get("serial_ports") or []
    board_ports = []
    instance_ids = []
    for port in ports:
        hwid = str(port.get("hwid") or "")
        device = str(port.get("device") or "")
        if BOARD_BRIDGE_VIDPID.replace("_", " ") in hwid.upper().replace(":", " "):
            board_ports.append(device)
            instance_ids.append(hwid)
        elif "USB VID:PID=1A86:55D3" in hwid.upper():
            board_ports.append(device)
            instance_ids.append(hwid)
    chosen = board_ports[0] if board_ports else None
    return chosen, instance_ids


def pick_native_usb_ports(summary: dict[str, Any]) -> list[str]:
    ports = summary.get("serial_ports") or []
    out: list[str] = []
    for port in ports:
        device = str(port.get("device") or "")
        hwid = str(port.get("hwid") or "").upper()
        desc = " ".join(
            str(port.get(k) or "")
            for k in ["description", "manufacturer", "product", "hwid"]
        ).upper()
        vid = port.get("vid")
        pid = port.get("pid")
        if (vid == 0x303A and pid == 0x1001) or "USB VID:PID=303A:1001" in hwid or "VID_303A&PID_1001" in desc:
            if device and device not in out:
                out.append(device)
    return out


def parse_hid_status_fields(hid_status_lines: list[str]) -> dict[str, Any]:
    if not hid_status_lines:
        return {
            "usb_mode": None,
            "control_channel": None,
            "hid_supported": None,
            "usb_started": None,
            "hid_ready": None,
        }

    last = hid_status_lines[-1]

    def extract(name: str) -> str | None:
        m = re.search(rf"\b{name}=([^\s]+)", last)
        return m.group(1) if m else None

    hid_supported_raw = extract("hid_supported")
    hid_supported = None
    if hid_supported_raw in {"0", "1"}:
        hid_supported = hid_supported_raw == "1"

    usb_started_raw = extract("usb_started")
    usb_started = None
    if usb_started_raw in {"0", "1"}:
        usb_started = usb_started_raw == "1"

    hid_ready_raw = extract("hid_ready")
    hid_ready = None
    if hid_ready_raw in {"0", "1"}:
        hid_ready = hid_ready_raw == "1"

    return {
        "usb_mode": extract("usb_mode"),
        "control_channel": extract("control_channel"),
        "hid_supported": hid_supported,
        "usb_started": usb_started,
        "hid_ready": hid_ready,
    }


def pick_board_port_from_host_text(host_text: str) -> tuple[str | None, list[str]]:
    ports: list[str] = []
    ids: list[str] = []
    for raw in host_text.splitlines():
        line = raw.strip()
        upper = line.upper()
        if "VID_1A86&PID_55D3" not in upper:
            continue
        ids.append(line)
        m = re.search(r"\((COM\d+)\)", line, flags=re.I)
        if m:
            ports.append(m.group(1).upper())
    return (ports[0] if ports else None), ids


def analyze_capture_dir(capture_dir: Path) -> CaptureAnalysis:
    summary = read_json(capture_dir / "summary.json")
    log_text = read_text(capture_dir / "capture.log")
    host_pnp = read_text(capture_dir / "host_pnp_usb.txt")
    host_cim = read_text(capture_dir / "host_cim_pnp.txt")
    host_all = host_pnp + "\n" + host_cim

    parsed_log = parse_capture_log(log_text)
    selected_port = (
        (summary.get("serial_session") or {}).get("port")
        or parsed_log["selected_port"]
    )
    serial_opened = bool((summary.get("serial_session") or {}).get("opened")) if summary else (selected_port is not None)
    serial_error = (
        (summary.get("serial_session") or {}).get("error")
        or parsed_log["serial_error"]
    )

    expected_board_port, bridge_instance_ids = pick_board_port(summary)
    if not expected_board_port:
        expected_board_port, fallback_ids = pick_board_port_from_host_text(host_all)
        if not bridge_instance_ids:
            bridge_instance_ids = fallback_ids
    native_usb_ports = pick_native_usb_ports(summary)

    preferred_port = native_usb_ports[0] if native_usb_ports else expected_board_port
    preferred_port_kind = "native_usb" if native_usb_ports else ("bridge" if expected_board_port else None)

    selected_matches_preferred = None
    if selected_port is not None and preferred_port is not None:
        selected_matches_preferred = selected_port.upper() == preferred_port.upper()

    native_candidates = find_native_candidates(host_all)
    bridge_present = (BOARD_BRIDGE_VIDPID in host_all.upper()) or bool(expected_board_port)

    hello_count = int(((summary.get("serial_session") or {}).get("stats") or {}).get("hello", 0) or parsed_log["hello_count"])
    ping_count = int(((summary.get("serial_session") or {}).get("stats") or {}).get("ping", 0) or parsed_log["ping_count"])
    hid_ready_count = int(((summary.get("serial_session") or {}).get("stats") or {}).get("hid_ready", 0) or parsed_log["hid_ready_count"])
    usb_started_count = int(((summary.get("serial_session") or {}).get("stats") or {}).get("usb_started", 0) or parsed_log["usb_started_count"])
    hid_status_lines = parsed_log["hid_status_lines"]
    hid_status_fields = parse_hid_status_fields(hid_status_lines)

    if hid_status_fields["usb_started"] is True:
        usb_started_count = max(usb_started_count, 1)
    if hid_status_fields["hid_ready"] is True:
        hid_ready_count = max(hid_ready_count, 1)

    likely_native_usb_enumerated = False
    for line in native_candidates:
        upper = line.upper()
        if "VID_303A" in upper or "ESP32" in upper or "TOUCH DIAL" in upper:
            likely_native_usb_enumerated = True

    conclusions: list[str] = []
    if expected_board_port:
        conclusions.append(f"板子桥口识别为 {expected_board_port}。")
    if preferred_port:
        if preferred_port_kind == "native_usb":
            conclusions.append(f"本次应优先使用原生 USB CDC：{preferred_port}。")
        elif preferred_port_kind == "bridge":
            conclusions.append(f"当前未发现 native USB CDC，桥口回退目标为 {preferred_port}。")
    if selected_port and preferred_port and selected_port.upper() != preferred_port.upper():
        if preferred_port_kind == "native_usb":
            conclusions.append(f"本次抓取选错串口：实际打开 {selected_port}，但当前应优先抓原生 USB CDC {preferred_port}。")
        else:
            conclusions.append(f"本次抓取选错串口：实际打开 {selected_port}，但当前桥口目标是 {preferred_port}。")
    elif selected_port and preferred_port and selected_port.upper() == preferred_port.upper() and preferred_port_kind == "native_usb":
        conclusions.append(f"本次串口抓取已优先选择了原生 USB CDC（{preferred_port}），没有误回落到桥口。")
    elif selected_port and preferred_port and selected_port.upper() == preferred_port.upper() and preferred_port_kind == "bridge":
        conclusions.append(f"本次串口抓取已正确回落到桥口（{preferred_port}）。")
    if serial_error:
        conclusions.append(f"串口抓取失败：{serial_error}。")
    if hid_status_lines:
        last = hid_status_lines[-1]
        conclusions.append(f"固件 HID 状态：{last.strip()}。")
    if hid_status_fields["control_channel"]:
        conclusions.append(f"固件当前控制通道={hid_status_fields['control_channel']}。")
    if hid_status_fields["usb_mode"] == "hwcdc" and hid_status_fields["hid_supported"] is False:
        conclusions.append("当前固件运行在 hwcdc 模式：native USB CDC 可用于命令/日志，但自定义 TinyUSB HID 不会启用；如需 HID，请切回 USBMode=default,CDCOnBoot=cdc。")
    elif hid_status_fields["usb_mode"] == "tinyusb" and hid_status_fields["hid_supported"] is True:
        conclusions.append("当前固件运行在 tinyusb 模式，且自定义 HID 路径已启用。")
    if usb_started_count == 0 and hid_ready_count == 0 and hid_status_lines and hid_status_fields["hid_supported"] is not False:
        conclusions.append("固件侧未观察到 USB started / HID ready，说明原生 USB 尚未被主机成功枚举。")
    if bridge_present:
        conclusions.append("Windows 已看到 CH343 串口桥（VID_1A86&PID_55D3）。")
    if not likely_native_usb_enumerated:
        conclusions.append("Windows 枚举信息中未发现明确的 ESP32/Espressif/VID_303A/Touch Dial 原生 USB 设备。")
    if likely_native_usb_enumerated:
        conclusions.append("Windows 枚举信息中发现疑似原生 USB 设备候选，需要进一步核对。")

    return CaptureAnalysis(
        capture_dir=str(capture_dir),
        started_at=summary.get("started_at") if summary else None,
        finished_at=summary.get("finished_at") if summary else None,
        selected_port=selected_port,
        expected_board_port=expected_board_port,
        preferred_port=preferred_port,
        preferred_port_kind=preferred_port_kind,
        selected_port_matches_preferred=selected_matches_preferred,
        serial_opened=serial_opened,
        serial_error=serial_error,
        hello_count=hello_count,
        ping_count=ping_count,
        hid_ready_count=hid_ready_count,
        usb_started_count=usb_started_count,
        hid_status_lines=hid_status_lines,
        usb_mode=hid_status_fields["usb_mode"],
        control_channel=hid_status_fields["control_channel"],
        hid_supported=hid_status_fields["hid_supported"],
        board_bridge_present=bridge_present,
        board_bridge_instance_ids=bridge_instance_ids,
        native_usb_ports=native_usb_ports,
        native_usb_candidates=native_candidates,
        likely_native_usb_enumerated=likely_native_usb_enumerated,
        conclusions=conclusions,
    )


def summarize_diffs(analyses: list[CaptureAnalysis], dirs: list[Path]) -> dict[str, Any]:
    device_sets = []
    for d in dirs:
        host_all = read_text(d / "host_pnp_usb.txt") + "\n" + read_text(d / "host_cim_pnp.txt")
        device_sets.append(set(extract_instance_ids(host_all)))

    diffs = []
    for i in range(1, len(device_sets)):
        added = sorted(device_sets[i] - device_sets[i - 1])
        removed = sorted(device_sets[i - 1] - device_sets[i])
        diffs.append({
            "from": str(dirs[i - 1]),
            "to": str(dirs[i]),
            "added": added,
            "removed": removed,
        })
    return {"pairwise_device_diffs": diffs}


def render_report(analyses: list[CaptureAnalysis], diff_info: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("HID capture analysis report")
    lines.append(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    for idx, item in enumerate(analyses, start=1):
        lines.append(f"[{idx}] {item.capture_dir}")
        lines.append(f"  selected_port: {item.selected_port}")
        lines.append(f"  expected_board_port: {item.expected_board_port}")
        lines.append(f"  preferred_port: {item.preferred_port}")
        lines.append(f"  preferred_port_kind: {item.preferred_port_kind}")
        lines.append(f"  selected_port_matches_preferred: {item.selected_port_matches_preferred}")
        lines.append(f"  serial_opened: {item.serial_opened}")
        lines.append(f"  serial_error: {item.serial_error}")
        lines.append(f"  hello_count: {item.hello_count}")
        lines.append(f"  ping_count: {item.ping_count}")
        lines.append(f"  usb_started_count: {item.usb_started_count}")
        lines.append(f"  hid_ready_count: {item.hid_ready_count}")
        lines.append(f"  usb_mode: {item.usb_mode}")
        lines.append(f"  control_channel: {item.control_channel}")
        lines.append(f"  hid_supported: {item.hid_supported}")
        lines.append(f"  board_bridge_present: {item.board_bridge_present}")
        lines.append(f"  likely_native_usb_enumerated: {item.likely_native_usb_enumerated}")
        if item.hid_status_lines:
            lines.append("  hid_status_lines:")
            for line in item.hid_status_lines:
                lines.append(f"    - {line.strip()}")
        if item.native_usb_candidates:
            lines.append("  native_usb_candidates:")
            for line in item.native_usb_candidates[:20]:
                lines.append(f"    - {line}")
        lines.append("  conclusions:")
        for c in item.conclusions:
            lines.append(f"    - {c}")
        lines.append("")

    lines.append("Global conclusion")
    wrong_ports = [a for a in analyses if a.selected_port and a.preferred_port and a.selected_port_matches_preferred is False]
    valid_runs = [
        a
        for a in analyses
        if a.serial_opened and not a.serial_error and a.selected_port and a.selected_port_matches_preferred is not False
    ]
    native_ok = any(a.likely_native_usb_enumerated for a in analyses)
    hid_ok = any(a.hid_ready_count > 0 or a.usb_started_count > 0 for a in analyses)
    hwcdc_only = any(a.usb_mode == "hwcdc" and a.hid_supported is False for a in analyses)

    if wrong_ports:
        lines.append(f"- 发现 {len(wrong_ports)} 次选错串口的抓取。")
    if valid_runs:
        lines.append(f"- 发现 {len(valid_runs)} 次有效串口抓取。")
    else:
        lines.append("- 本次输入中没有有效串口抓取；当前结论基于主机枚举信息。")
    if valid_runs and not hid_ok and hwcdc_only:
        lines.append("- 有效串口抓取已经落在 native USB CDC，但当前固件处于 hwcdc 模式，因此不会出现自定义 TinyUSB HID ready。")
    elif valid_runs and not hid_ok:
        lines.append("- 所有有效抓取都未出现 USB started / HID ready。")
    if not native_ok:
        lines.append("- 所有抓取的 Windows 枚举信息里都未发现明确的 ESP32/Espressif/VID_303A/Touch Dial 原生 USB 设备。")
    if native_ok and not valid_runs:
        lines.append("- 主机枚举已发现 VID_303A 原生 USB 设备，说明 ESP32-S3 native USB 已经被 Windows 看到。")
    if valid_runs and not hid_ok and not native_ok:
        lines.append("- 综合判断：当前只看到 CH343 串口桥，未看到 ESP32-S3 原生 USB 链路；问题仍在 native USB 物理连接/接线/接口路径。")
    lines.append("")

    for pair in diff_info.get("pairwise_device_diffs", []):
        lines.append(f"Diff: {pair['from']} -> {pair['to']}")
        if pair["added"]:
            lines.append("  added:")
            for row in pair["added"][:50]:
                lines.append(f"    + {row}")
        if pair["removed"]:
            lines.append("  removed:")
            for row in pair["removed"][:50]:
                lines.append(f"    - {row}")
        if not pair["added"] and not pair["removed"]:
            lines.append("  no device-instance diff detected")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze one or more HID capture directories and emit root-cause oriented conclusions")
    p.add_argument("capture_dirs", nargs="+", help="One or more capture directories")
    p.add_argument("--out-dir", default=None, help="Where to write analysis_report.txt/json; default: first capture dir")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    dirs = [Path(x).expanduser().resolve() for x in args.capture_dirs]
    analyses = [analyze_capture_dir(d) for d in dirs]
    diff_info = summarize_diffs(analyses, dirs)
    report = render_report(analyses, diff_info)

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else dirs[0]
    out_dir.mkdir(parents=True, exist_ok=True)
    text_path = out_dir / "analysis_report.txt"
    json_path = out_dir / "analysis_report.json"
    text_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "captures": [asdict(a) for a in analyses],
                "diffs": diff_info,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(report)
    print()
    print(f"Wrote: {text_path}")
    print(f"Wrote: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
