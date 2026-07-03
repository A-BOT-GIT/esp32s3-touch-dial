from pathlib import Path

from tools.analyze_hid_captures import analyze_capture_dir, render_report


def test_analyze_capture_dir_detects_wrong_port_and_no_native_usb(tmp_path: Path):
    d = tmp_path / "cap"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-02 16:01:28",
  "finished_at": "2026-07-02 16:01:40",
  "serial_ports": [
    {"device": "COM14", "hwid": "USB VID:PID=1A86:55D3 SER=5B91003578 LOCATION=1-1.1.4"}
  ],
  "serial_session": {
    "port": "COM7",
    "opened": true,
    "stats": {"hello": 0, "ping": 0, "hid_ready": 0, "usb_started": 0},
    "error": "SerialTimeoutException('Write timeout')"
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-02 16:01:37] opening serial port COM7 @ 115200
[2026-07-02 16:01:40] serial capture failed: SerialTimeoutException('Write timeout')
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        "Ports    OK     USB-Enhanced-SERIAL CH343 (COM14)                     USB\\VID_1A86&PID_55D3\\5B91003578\n",
        encoding="utf-8",
    )
    (d / "host_cim_pnp.txt").write_text(
        "PNPClass     : Ports\nDeviceID     : USB\\VID_1A86&PID_55D3\\5B91003578\n",
        encoding="utf-8",
    )

    result = analyze_capture_dir(d)

    assert result.expected_board_port == "COM14"
    assert result.preferred_port == "COM14"
    assert result.selected_port == "COM7"
    assert result.selected_port_matches_preferred is False
    assert result.likely_native_usb_enumerated is False
    assert any("选错串口" in x for x in result.conclusions)


def test_analyze_capture_dir_prefers_native_usb_over_bridge(tmp_path: Path):
    d = tmp_path / "cap_native"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-02 18:03:01",
  "finished_at": "2026-07-02 18:03:20",
  "serial_ports": [
    {"device": "COM14", "hwid": "USB VID:PID=1A86:55D3 SER=5B91003578 LOCATION=1-1.1.4", "vid": 6790, "pid": 21971},
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.3", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 1, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-02 18:03:04] opening serial port COM16 @ 115200
[2026-07-02 18:03:05] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 product=ESP32-S3 Touch Dial note=switch_to_USBMode_default_CDCOnBoot_cdc_for_custom_hid
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB-Enhanced-SERIAL CH343 (COM14)                     USB\\VID_1A86&PID_55D3\\5B91003578
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
HIDClass OK     ESP32-S3 Touch Dial                                  HID\\VID_303A&PID_1001&MI_03\\9&111111&0&0000
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_cim_pnp.txt").write_text(
        """
Name         : USB JTAG/Serial debug unit (COM16)
DeviceID     : USB\\VID_303A&PID_1001\\288485B5FD78
Manufacturer : Espressif
Status       : OK
        """.strip(),
        encoding="utf-8",
    )

    result = analyze_capture_dir(d)

    assert result.expected_board_port == "COM14"
    assert result.preferred_port == "COM16"
    assert result.selected_port == "COM16"
    assert result.selected_port_matches_preferred is True
    assert result.preferred_port_kind == "native_usb"
    assert result.control_channel == "native_usb_hwcdc"
    assert result.usb_mode == "hwcdc"
    assert result.hid_supported is False
    assert result.likely_native_usb_enumerated is True
    assert not any("选错串口" in x for x in result.conclusions)
    assert any("优先选择了原生 USB CDC" in x for x in result.conclusions)
    assert any("当前固件运行在 hwcdc 模式" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "preferred_port: COM16" in report
    assert "control_channel: native_usb_hwcdc" in report


def test_analyze_capture_dir_uses_hid_status_fields_when_event_lines_absent(tmp_path: Path):
    d = tmp_path / "cap_tinyusb_ready"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 03:28:21",
  "finished_at": "2026-07-03 03:28:56",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB Serial Device (COM16)", "manufacturer": "Microsoft"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 13, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 03:28:26] opening serial port COM16 @ 115200
[2026-07-03 03:28:28] [rx] >HID_STATUS reason=serial_cmd usb_mode=tinyusb cdc_on_boot=1 control_channel=native_usb_tinyusb_cdc hid_supported=1 usb_started=1 hid_ready=1 product=ESP32-S3 Touch Dial
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB Serial Device (COM16)                              USB\\VID_303A&PID_1001&MI_01\\8&FCCDD52&0&0001
HIDClass OK     ESP32-S3 Touch Dial                                    HID\\VID_303A&PID_1001&MI_00\\9&111111&0&0000
USB      OK     USB Composite Device                                   USB\\VID_303A&PID_1001\\288485B5FD78
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_cim_pnp.txt").write_text(
        """
Name         : USB Serial Device (COM16)
DeviceID     : USB\\VID_303A&PID_1001\\288485B5FD78
Manufacturer : Microsoft
Status       : OK
        """.strip(),
        encoding="utf-8",
    )

    result = analyze_capture_dir(d)

    assert result.preferred_port == "COM16"
    assert result.selected_port == "COM16"
    assert result.usb_mode == "tinyusb"
    assert result.control_channel == "native_usb_tinyusb_cdc"
    assert result.hid_supported is True
    assert result.usb_started_count == 1
    assert result.hid_ready_count == 1
    assert any("tinyusb 模式" in x for x in result.conclusions)
    assert not any("未观察到 USB started / HID ready" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "usb_started_count: 1" in report
    assert "hid_ready_count: 1" in report
    assert "所有有效抓取都未出现 USB started / HID ready" not in report
