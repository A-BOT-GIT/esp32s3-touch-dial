#!/usr/bin/env python3
"""
ESP32-S3 Radial MVP — Windows Raw HID 中文监听入口

用途：
  1. 列出 Windows HID 设备并优先标记疑似 ESP32-S3 Radial MVP
  2. 监听主机是否真的收到了来自设备的 HID 输入报告

相比旧版临时脚本，这个入口：
  - 不再使用错误的默认 VID/PID
  - 默认优先按名称 "ESP32" 搜索
  - 仍可手工指定 path / vid / pid

常用命令：
  python raw_hid_listener_cn.py list
  python raw_hid_listener_cn.py listen
  python raw_hid_listener_cn.py listen --name "ESP32" --timeout 120
  python raw_hid_listener_cn.py listen --path "\\\\?\\HID#..."
"""

from __future__ import annotations

import argparse
import sys

import hid_probe


DEFAULT_VID = 0x303A
DEFAULT_NAME = "ESP32"


def print_title() -> None:
    print("=" * 72)
    print("ESP32-S3 Radial MVP Raw HID 中文监听器")
    print("=" * 72)
    print("用途：确认 Windows 主机是否实际收到了设备发出的 HID 输入报告。")
    print("建议流程：")
    print("  1. 先在 Windows 上确认蓝牙设备已连接。")
    print("  2. 在 Linux 侧执行 LOG QUIET，减少串口刷屏。")
    print("  3. 先运行本脚本 list 看设备。")
    print("  4. 再运行本脚本 listen 开始监听。")
    print("  5. 最后在 Linux 串口执行 RADIAL TEST CW / DOWN / UP。")
    print("=" * 72)
    print()


def parse_hex_int(value: str, name: str) -> int:
    try:
        return int(str(value).replace("0x", "").replace("0X", ""), 16)
    except Exception:
        print(f"错误：{name} 不是有效十六进制数：{value}")
        raise SystemExit(2)


def print_list_hint() -> None:
    print()
    print("说明：")
    print("  - 优先看 score 较高、名称里带 ESP32 / Radial / BTHLE 的设备。")
    print("  - 如果看到多个候选，后续监听优先用 --path 精确指定。")
    print("  - 如果完全看不到相关设备，再检查 Windows 蓝牙连接状态。")


def print_listen_hint(args: argparse.Namespace) -> None:
    print("监听参数：")
    if args.path:
        print(f"  path   = {args.path}")
    elif args.vid is not None and args.pid is not None:
        print(f"  vid/pid= 0x{args.vid:04X}/0x{args.pid:04X}")
    else:
        print(f"  name   = {args.name}")
    print(f"  timeout= {args.timeout}s")
    print()
    print("收到报告时，重点关注：")
    print("  - 右转测试：00 64 00   (delta=+100, +10.0 deg)")
    print("  - 左转测试：00 9C FF   (delta=-100, -10.0 deg)")
    print("  - 按下测试：01 00 00")
    print("  - 松开测试：00 00 00")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ESP32-S3 Radial MVP Raw HID 中文监听器"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="列出 HID 设备并标记疑似 ESP32 候选")

    listen = sub.add_parser("listen", help="监听 HID 输入报告")
    listen.add_argument("--path", help="设备路径，例如 \\\\?\\HID#...")
    listen.add_argument("--vid", help="VID，十六进制，例如 303A")
    listen.add_argument("--pid", help="PID，十六进制，例如 1001")
    listen.add_argument("--name", default=DEFAULT_NAME, help='按名称筛选，默认 "ESP32"')
    listen.add_argument("--timeout", type=int, default=120, help="监听秒数，默认 120")

    return parser


def main() -> None:
    print_title()
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        hid_probe.list_devices()
        print_list_hint()
        return

    if args.command == "listen":
        vid = parse_hex_int(args.vid, "VID") if args.vid else None
        pid = parse_hex_int(args.pid, "PID") if args.pid else None

        if (vid is None) ^ (pid is None):
            print("错误：--vid 和 --pid 必须一起提供。")
            raise SystemExit(2)

        print_listen_hint(
            argparse.Namespace(
                path=args.path,
                vid=vid,
                pid=pid,
                name=args.name,
                timeout=args.timeout,
            )
        )

        if args.path:
            hid_probe.listen_reports(path=args.path, timeout=args.timeout)
            return

        if vid is not None and pid is not None:
            hid_probe.listen_reports(vid=vid, pid=pid, timeout=args.timeout)
            return

        hid_probe.listen_reports(name_filter=args.name, timeout=args.timeout)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
