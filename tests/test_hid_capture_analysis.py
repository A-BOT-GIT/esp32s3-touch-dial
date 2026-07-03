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


def test_analyze_capture_dir_detects_linux_native_usb_and_avoids_windows_only_conclusion(tmp_path: Path):
    d = tmp_path / "cap_linux_native"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-04 01:31:16",
  "finished_at": "2026-07-04 01:31:38",
  "serial_ports": [
    {"device": "/dev/ttyACM0", "hwid": "USB VID:PID=303A:1001 SER=28:84:85:B5:FD:78 LOCATION=1-2.1:1.0", "vid": 12346, "pid": 4097, "description": "USB JTAG/serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "/dev/ttyACM0",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_lsusb.txt").write_text(
        "Bus 001 Device 021: ID 303a:1001 Espressif USB JTAG/serial debug unit\n",
        encoding="utf-8",
    )
    (d / "host_usb_devices.txt").write_text(
        "== 1-2.1 ==\nvendor: 303a\nproduct: 1001\nmanufacturer: Espressif\nproduct_name: USB JTAG/serial debug unit\n",
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-04 01:31:16] opening serial port /dev/ttyACM0 @ 115200
[2026-07-04 01:31:20] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=0 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=0 backend_status=advertising ble_connected=0 ble_advertising=1 product=ESP32-S3 Touch Dial note=ble_dial_advertising last_backend_error=none last_send_type=none
        """.strip(),
        encoding="utf-8",
    )

    result = analyze_capture_dir(d)

    assert result.preferred_port == "/dev/ttyACM0"
    assert result.preferred_port_kind == "native_usb"
    assert result.selected_port == "/dev/ttyACM0"
    assert result.selected_port_matches_preferred is True
    assert result.likely_native_usb_enumerated is True
    assert not any("Windows 枚举信息中未发现" in x for x in result.conclusions)
    assert any("主机枚举信息中发现疑似原生 USB 设备候选" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "所有抓取的 Windows 枚举信息里都未发现明确的 ESP32/Espressif/VID_303A/Touch Dial 原生 USB 设备" not in report


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


def test_analyze_capture_dir_reports_ble_backend_skeleton_not_ready(tmp_path: Path):
    d = tmp_path / "cap_ble_backend"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 11:18:21",
  "finished_at": "2026-07-03 11:18:40",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 11:18:22] opening serial port COM16 @ 115200
[2026-07-03 11:18:24] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=0 backend_status=stub_idle product=ESP32-S3 Touch Dial note=ble_dial_backend_skeleton_waiting_for_connection
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
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

    assert result.preferred_port == "COM16"
    assert result.usb_mode == "hwcdc"
    assert result.control_channel == "native_usb_hwcdc"
    assert result.hid_supported is False
    assert result.dial_backend == "ble_hid_dial"
    assert result.dial_backend_ready is False
    assert result.backend_status == "stub_idle"
    assert any("BLE Dial backend 骨架已启用" in x for x in result.conclusions)
    assert any("当前 backend 尚未 ready" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "dial_backend: ble_hid_dial" in report
    assert "dial_backend_ready: False" in report
    assert "backend_status: stub_idle" in report


def test_analyze_capture_dir_reports_ble_advertising_state_fields(tmp_path: Path):
    d = tmp_path / "cap_ble_advertising"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 12:01:01",
  "finished_at": "2026-07-03 12:01:25",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 12:01:02] opening serial port COM16 @ 115200
[2026-07-03 12:01:03] [rx] >HID_STATUS reason=ble_advertising_start usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=0 backend_status=advertising ble_connected=0 ble_advertising=1 product=ESP32-S3 Touch Dial note=ble_dial_advertising last_backend_error=none last_send_type=none
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                                  BTHENUM\\DEV_001122334455\\8&111111&0&BLUETOOTHDEVICE_001122334455
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

    assert result.dial_backend == "ble_hid_dial"
    assert result.dial_backend_ready is False
    assert result.backend_status == "advertising"
    assert result.ble_connected is False
    assert result.ble_advertising is True
    assert any("BLE advertising 已启动" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "ble_connected: False" in report
    assert "ble_advertising: True" in report


def test_analyze_capture_dir_interprets_ble_send_semantics_fields(tmp_path: Path):
    d = tmp_path / "cap_ble_send_semantics"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 12:09:01",
  "finished_at": "2026-07-03 12:09:25",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 12:09:02] opening serial port COM16 @ 115200
[2026-07-03 12:09:08] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=0 backend_status=advertising ble_connected=0 ble_advertising=1 product=ESP32-S3 Touch Dial note=ble_dial_advertising last_backend_error=report_missing last_send_type=rotate_right
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                                  BTHENUM\\DEV_001122334455\\8&111111&0&BLUETOOTHDEVICE_001122334455
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

    assert result.last_send_type == "rotate_right"
    assert result.last_backend_error == "report_missing"
    assert any("最近一次 BLE backend 发送是右旋相对增量" in x for x in result.conclusions)
    assert any("BLE input report 特征缺失，发送路径当前不可用" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "last_backend_error: report_missing" in report
    assert "last_send_type: rotate_right" in report


def test_analyze_capture_dir_interprets_ble_press_send_semantics_fields(tmp_path: Path):
    d = tmp_path / "cap_ble_press_send_semantics"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 12:15:01",
  "finished_at": "2026-07-03 12:15:25",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 12:15:02] opening serial port COM16 @ 115200
[2026-07-03 12:15:08] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=1 backend_status=connected_idle ble_connected=1 ble_advertising=0 product=ESP32-S3 Touch Dial note=ble_dial_link_established last_backend_error=none last_send_type=press
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                                  BTHENUM\\DEV_001122334455\\8&111111&0&BLUETOOTHDEVICE_001122334455
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

    assert result.last_send_type == "press"
    assert result.last_backend_error == "none"
    assert any("最近一次 BLE backend 发送是按压脉冲" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "last_send_type: press" in report


def test_analyze_capture_dir_interprets_ble_not_ready_error(tmp_path: Path):
    d = tmp_path / "cap_ble_not_ready"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 12:17:01",
  "finished_at": "2026-07-03 12:17:25",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 12:17:02] opening serial port COM16 @ 115200
[2026-07-03 12:17:08] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=0 backend_status=advertising ble_connected=0 ble_advertising=1 product=ESP32-S3 Touch Dial note=ble_dial_advertising last_backend_error=not_ready last_send_type=press
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                                  BTHENUM\\DEV_001122334455\\8&111111&0&BLUETOOTHDEVICE_001122334455
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

    assert result.last_send_type == "press"
    assert result.last_backend_error == "not_ready"
    assert any("BLE backend 尚未 ready，最近一次发送被跳过" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "last_backend_error: not_ready" in report


def test_analyze_capture_dir_interprets_ble_rate_limited_rotate_error(tmp_path: Path):
    d = tmp_path / "cap_ble_rate_limited_rotate"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 12:21:01",
  "finished_at": "2026-07-03 12:21:25",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 12:21:02] opening serial port COM16 @ 115200
[2026-07-03 12:21:08] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=1 backend_status=connected_idle ble_connected=1 ble_advertising=0 product=ESP32-S3 Touch Dial note=ble_dial_link_established last_backend_error=rate_limited_rotate last_send_type=rotate_right
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                                  BTHENUM\\DEV_001122334455\\8&111111&0&BLUETOOTHDEVICE_001122334455
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

    assert result.last_backend_error == "rate_limited_rotate"
    assert any("BLE rotate 发送因节流被跳过" in x for x in result.conclusions)


def test_analyze_capture_dir_interprets_ble_rate_limited_press_error(tmp_path: Path):
    d = tmp_path / "cap_ble_rate_limited_press"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 12:23:01",
  "finished_at": "2026-07-03 12:23:25",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 12:23:02] opening serial port COM16 @ 115200
[2026-07-03 12:23:08] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=1 backend_status=connected_idle ble_connected=1 ble_advertising=0 product=ESP32-S3 Touch Dial note=ble_dial_link_established last_backend_error=rate_limited_press last_send_type=press
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                                  BTHENUM\\DEV_001122334455\\8&111111&0&BLUETOOTHDEVICE_001122334455
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

    assert result.last_backend_error == "rate_limited_press"
    assert any("BLE press 发送因节流被跳过" in x for x in result.conclusions)


def test_analyze_capture_dir_reports_ble_backend_ready(tmp_path: Path):
    d = tmp_path / "cap_ble_ready"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 11:40:01",
  "finished_at": "2026-07-03 11:40:25",
  "serial_ports": [
    {"device": "COM16", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.4:x.1", "vid": 12346, "pid": 4097, "description": "USB JTAG/Serial debug unit", "manufacturer": "Espressif"}
  ],
  "serial_session": {
    "port": "COM16",
    "opened": true,
    "stats": {"hello": 1, "ping": 2, "hid_ready": 0, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 11:40:02] opening serial port COM16 @ 115200
[2026-07-03 11:40:08] [rx] >HID_STATUS reason=ready_edge usb_mode=hwcdc cdc_on_boot=1 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=1 backend_status=connected_idle product=ESP32-S3 Touch Dial note=ble_dial_link_established
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB JTAG/Serial debug unit (COM16)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                                  BTHENUM\\DEV_001122334455\\8&111111&0&BLUETOOTHDEVICE_001122334455
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

    assert result.dial_backend == "ble_hid_dial"
    assert result.dial_backend_ready is True
    assert result.backend_status == "connected_idle"
    assert any("BLE Dial backend 骨架已启用" in x for x in result.conclusions)
    assert any("当前 backend 已 ready" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "dial_backend_ready: True" in report
    assert "backend_status: connected_idle" in report


def test_analyze_capture_dir_flags_ble_connection_storm_as_input_blocker(tmp_path: Path):
    d = tmp_path / "cap_ble_connection_storm"
    d.mkdir()
    (d / "summary.json").write_text(
        """
{
  "started_at": "2026-07-03 21:28:33",
  "finished_at": "2026-07-03 21:29:23",
  "serial_ports": [
    {"device": "COM15", "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78", "vid": 12346, "pid": 4097, "description": "USB 串行设备 (COM15)", "manufacturer": "Microsoft"}
  ],
  "serial_session": {
    "port": "COM15",
    "opened": true,
    "stats": {"hello": 1, "ping": 21, "hid_ready": 2, "usb_started": 0}
  }
}
        """.strip(),
        encoding="utf-8",
    )
    (d / "capture.log").write_text(
        """
[2026-07-03 21:28:39] [rx] >BLE connected
[2026-07-03 21:28:39] [rx] >HID_STATUS reason=ble_connect usb_mode=hwcdc cdc_on_boot=0 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=1 backend_status=connected_idle ble_connected=1 ble_advertising=0 product=ESP32-S3 Touch Dial note=ble_dial_link_established last_backend_error=none last_send_type=none
[2026-07-03 21:28:39] [rx] >BLE disconnected
[2026-07-03 21:28:39] [rx] >BLE advertising restart
[2026-07-03 21:28:39] [rx] >HID_STATUS reason=ble_disconnect usb_mode=hwcdc cdc_on_boot=0 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=0 backend_status=advertising ble_connected=0 ble_advertising=1 product=ESP32-S3 Touch Dial note=ble_dial_advertising last_backend_error=none last_send_type=none
[2026-07-03 21:29:22] [rx] >BLE report rotate delta=-1
[2026-07-03 21:29:22] [rx] >BLE report skip reason=not_ready
[2026-07-03 21:29:22] [rx] >ENC source=ENC dir=LEFT volume=48 hid=skip ready=no backend=ble_hid_dial
[2026-07-03 21:29:22] [rx] >HID_STATUS reason=serial_cmd usb_mode=hwcdc cdc_on_boot=0 control_channel=native_usb_hwcdc hid_supported=0 usb_started=0 hid_ready=0 dial_backend=ble_hid_dial dial_backend_ready=0 backend_status=advertising ble_connected=0 ble_advertising=1 product=ESP32-S3 Touch Dial note=ble_dial_advertising last_backend_error=not_ready last_send_type=rotate_left
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_pnp_usb.txt").write_text(
        """
Ports    OK     USB 串行设备 (COM15)                   USB\\VID_303A&PID_1001\\288485B5FD78
BTHENUM  OK     Bluetooth LE Device                    BTHENUM\\DEV_F4F31824918E\\8&111111&0&BLUETOOTHDEVICE_F4F31824918E
        """.strip(),
        encoding="utf-8",
    )
    (d / "host_cim_pnp.txt").write_text(
        """
Name         : ESP32-S3 Touch Dial
PNPClass     : Bluetooth
DeviceID     : BTHLE\\DEV_F4F31824918E\\7&2852A423&0&F4F31824918E
Manufacturer : Microsoft
Status       : OK
        """.strip(),
        encoding="utf-8",
    )

    result = analyze_capture_dir(d)

    assert any("BLE 连接存在反复 connect/disconnect 抖动" in x for x in result.conclusions)
    assert any("旋钮事件已到达 BLE backend，但因链路未稳定/未 ready 尚未进入 Windows 可用输入路径" in x for x in result.conclusions)

    report = render_report([result], {"pairwise_device_diffs": []})
    assert "last_backend_error: not_ready" in report
    assert "last_send_type: rotate_left" in report
