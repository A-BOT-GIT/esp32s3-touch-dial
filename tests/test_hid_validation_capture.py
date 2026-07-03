import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "hid_validation_capture.py"


def load_module():
    spec = importlib.util.spec_from_file_location("hid_validation_capture", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_autodetect_port_prefers_native_usb_over_bridge(monkeypatch):
    mod = load_module()

    monkeypatch.setattr(
        mod,
        "list_serial_ports",
        lambda: [
            {
                "device": "COM14",
                "description": "USB-Enhanced-SERIAL CH343",
                "manufacturer": "wch.cn",
                "product": None,
                "vid": 0x1A86,
                "pid": 0x55D3,
                "serial_number": "5B91003578",
                "location": "1-1.1.4",
                "hwid": "USB VID:PID=1A86:55D3 SER=5B91003578 LOCATION=1-1.1.4",
            },
            {
                "device": "COM16",
                "description": "USB JTAG/Serial debug unit",
                "manufacturer": "Espressif",
                "product": "USB JTAG/serial debug unit",
                "vid": 0x303A,
                "pid": 0x1001,
                "serial_number": "288485B5FD78",
                "location": "1-1.1.3",
                "hwid": "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.3",
            },
        ],
    )

    assert mod.autodetect_port() == "COM16"


def test_autodetect_port_falls_back_to_bridge_when_native_missing(monkeypatch):
    mod = load_module()

    monkeypatch.setattr(
        mod,
        "list_serial_ports",
        lambda: [
            {
                "device": "COM14",
                "description": "USB-Enhanced-SERIAL CH343",
                "manufacturer": "wch.cn",
                "product": None,
                "vid": 0x1A86,
                "pid": 0x55D3,
                "serial_number": "5B91003578",
                "location": "1-1.1.4",
                "hwid": "USB VID:PID=1A86:55D3 SER=5B91003578 LOCATION=1-1.1.4",
            }
        ],
    )

    assert mod.autodetect_port() == "COM14"
