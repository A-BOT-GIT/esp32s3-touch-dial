import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "dial_listener.py"


def load_module():
    spec = importlib.util.spec_from_file_location("dial_listener", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeSerial:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)


class FakeRunner:
    def __init__(self):
        self.actions = []
        self.volumes = []

    def run(self, action, source):
        self.actions.append((action, source))

    def run_volume(self, value, source):
        self.volumes.append((value, source))


def test_serial_volume_line_dispatches_absolute_volume():
    mod = load_module()
    runner = FakeRunner()
    reader = mod.SerialReader(runner)

    reader._handle_line(">VOLUME 37")

    assert runner.volumes == [(37, "serial")]
    assert runner.actions == []


def test_serial_mute_toggle_line_dispatches_action():
    mod = load_module()
    runner = FakeRunner()
    reader = mod.SerialReader(runner)

    reader._handle_line(">MUTE_TOGGLE")

    assert runner.actions == [("mute_toggle", "serial")]


def test_hello_and_ping_still_ack():
    mod = load_module()
    runner = FakeRunner()
    reader = mod.SerialReader(runner)
    reader._ser = FakeSerial()

    reader._handle_line(">HELLO")
    reader._handle_line(">PING")

    assert reader._ser.writes == [b"ACK\n", b"ACK\n"]


def test_serial_port_scan_matches_usb_single_serial_device(monkeypatch):
    mod = load_module()

    class FakePort:
        device = "/dev/ttyACM0"
        description = "USB Single Serial"
        manufacturer = None

    monkeypatch.setattr(mod.serial.tools.list_ports, "comports", lambda: [FakePort()])

    reader = mod.SerialReader(FakeRunner())

    assert reader._find_port() == "/dev/ttyACM0"


def test_serial_port_scan_uses_manual_env_port(monkeypatch):
    mod = load_module()

    monkeypatch.setenv("DIAL_SERIAL_PORT", "COM12")
    monkeypatch.setattr(mod.serial.tools.list_ports, "comports", lambda: [])

    reader = mod.SerialReader(FakeRunner())

    assert reader._find_port() == "COM12"


def test_serial_port_scan_matches_esp32s3_native_usb_vid_pid(monkeypatch):
    mod = load_module()

    class FakePort:
        device = "COM7"
        description = "USB JTAG/serial debug unit"
        manufacturer = "Espressif"
        hwid = "USB VID:PID=303A:1001 SER=284485B5FD78"
        vid = 0x303A
        pid = 0x1001

    monkeypatch.setattr(mod.serial.tools.list_ports, "comports", lambda: [FakePort()])

    reader = mod.SerialReader(FakeRunner())

    assert reader._find_port() == "COM7"


def test_serial_port_scan_matches_esp32s3_even_when_description_is_generic(monkeypatch):
    mod = load_module()

    class FakePort:
        device = "COM8"
        description = "USB Serial Device"
        manufacturer = None
        hwid = "USB VID:PID=303A:1001"
        vid = 0x303A
        pid = 0x1001

    monkeypatch.setattr(mod.serial.tools.list_ports, "comports", lambda: [FakePort()])

    reader = mod.SerialReader(FakeRunner())

    assert reader._find_port() == "COM8"


def test_serial_port_scan_matches_esp32s3_by_vid_pid_when_names_are_generic(monkeypatch):
    mod = load_module()

    class FakePort:
        device = "COM9"
        description = "USB Composite Device"
        manufacturer = None
        hwid = "USB VID:PID=303A:1001"
        vid = 0x303A
        pid = 0x1001

    monkeypatch.setattr(mod.serial.tools.list_ports, "comports", lambda: [FakePort()])

    reader = mod.SerialReader(FakeRunner())

    assert reader._find_port() == "COM9"


def test_serial_port_scan_prefers_native_usb_cdc_over_bridge_port(monkeypatch):
    mod = load_module()

    class BridgePort:
        device = "COM14"
        description = "USB-Enhanced-SERIAL CH343"
        manufacturer = "wch.cn"
        hwid = "USB VID:PID=1A86:55D3 SER=5B91003578 LOCATION=1-1.1.4"
        vid = 0x1A86
        pid = 0x55D3

    class NativePort:
        device = "COM16"
        description = "USB JTAG/Serial debug unit"
        manufacturer = "Espressif"
        hwid = "USB VID:PID=303A:1001 SER=288485B5FD78 LOCATION=1-1.1.3"
        vid = 0x303A
        pid = 0x1001

    monkeypatch.setattr(mod.serial.tools.list_ports, "comports", lambda: [BridgePort(), NativePort()])

    reader = mod.SerialReader(FakeRunner())

    assert reader._find_port() == "COM16"


def test_plain_press_line_from_touch_firmware_dispatches_press():
    mod = load_module()
    runner = FakeRunner()
    reader = mod.SerialReader(runner)

    reader._handle_line(">PRESS")

    assert runner.actions == [("press", "serial")]


def test_audio_controller_initializes_com_before_get_speakers(monkeypatch):
    mod = load_module()
    events = []

    class FakeDevice:
        id = "fake-device"
        FriendlyName = "Fake Speaker"
        EndpointVolume = object()

    class FakeAudioUtilities:
        @staticmethod
        def GetSpeakers():
            events.append("get_speakers")
            return FakeDevice()

    monkeypatch.setattr(mod, "_HAS_PYCAW", True)
    monkeypatch.setattr(mod, "AudioUtilities", FakeAudioUtilities, raising=False)
    monkeypatch.setattr(mod, "CoInitialize", lambda: events.append("coinit"), raising=False)
    monkeypatch.setattr(mod, "PRIMARY_TARGET_AUDIO_NAME", "Fake Speaker", raising=False)
    monkeypatch.setattr(mod, "FALLBACK_TARGET_AUDIO_NAME", "", raising=False)

    audio = mod.AudioController()

    assert audio._ensure_active_device() is True
    assert events[:2] == ["coinit", "get_speakers"]


def test_audio_controller_prefers_realtek_speaker_device(monkeypatch):
    mod = load_module()

    class FakeDevice:
        def __init__(self, dev_id, name):
            self.id = dev_id
            self.FriendlyName = name
            self.EndpointVolume = object()

    devices = [
        FakeDevice("dev-surround", "扬声器 (7.1 Surround Sound)"),
        FakeDevice("dev-realtek-2nd", "Realtek HD Audio 2nd output (Realtek(R) Audio)"),
        FakeDevice("dev-realtek-speaker", "扬声器 (Realtek(R) Audio)"),
    ]

    class FakeAudioUtilities:
        @staticmethod
        def GetSpeakers():
            return devices[0]

        @staticmethod
        def GetAllDevices():
            return devices

    monkeypatch.setattr(mod, "_HAS_PYCAW", True)
    monkeypatch.setattr(mod, "AudioUtilities", FakeAudioUtilities, raising=False)
    monkeypatch.setattr(mod, "CoInitialize", lambda: None, raising=False)

    audio = mod.AudioController()

    assert audio._ensure_active_device() is True
    assert audio._last_dev_id == "dev-realtek-speaker"


def test_audio_controller_falls_back_to_surround_speaker_when_realtek_missing(monkeypatch):
    mod = load_module()

    class FakeDevice:
        def __init__(self, dev_id, name):
            self.id = dev_id
            self.FriendlyName = name
            self.EndpointVolume = object()

    devices = [
        FakeDevice("dev-usb", "扬声器 (USB Audio)"),
        FakeDevice("dev-surround", "扬声器 (7.1 Surround Sound)"),
    ]

    class FakeAudioUtilities:
        @staticmethod
        def GetSpeakers():
            return devices[0]

        @staticmethod
        def GetAllDevices():
            return devices

    monkeypatch.setattr(mod, "_HAS_PYCAW", True)
    monkeypatch.setattr(mod, "AudioUtilities", FakeAudioUtilities, raising=False)
    monkeypatch.setattr(mod, "CoInitialize", lambda: None, raising=False)

    audio = mod.AudioController()

    assert audio._ensure_active_device() is True
    assert audio._last_dev_id == "dev-surround"


def test_audio_controller_set_volume_clamps_to_scalar():
    mod = load_module()

    class FakeVolumeInterface:
        def __init__(self):
            self.values = []

        def SetMasterVolumeLevelScalar(self, value, event_context):
            self.values.append((value, event_context))

    audio = mod.AudioController()
    iface = FakeVolumeInterface()
    audio._vol_iface = iface
    audio._ensure_active_device = lambda: True

    assert audio.set_volume_percent(150) is True
    assert iface.values[-1] == (1.0, None)

    assert audio.set_volume_percent(-20) is True
    assert iface.values[-1] == (0.0, None)

    assert audio.set_volume_percent(37) is True
    assert iface.values[-1] == (0.37, None)


def test_audio_controller_list_audio_devices_reports_default_and_target(monkeypatch):
    mod = load_module()

    class FakeDevice:
        def __init__(self, dev_id, name):
            self.id = dev_id
            self.FriendlyName = name
            self.EndpointVolume = object()

    default = FakeDevice("dev-default", "扬声器 (USB Audio)")
    realtek = FakeDevice("dev-realtek", "Realtek HD Audio 2nd output (Realtek(R) Audio)")
    devices = [default, realtek]

    class FakeAudioUtilities:
        @staticmethod
        def GetSpeakers():
            return default

        @staticmethod
        def GetAllDevices():
            return devices

    monkeypatch.setattr(mod, "_HAS_PYCAW", True)
    monkeypatch.setattr(mod, "AudioUtilities", FakeAudioUtilities, raising=False)
    monkeypatch.setattr(mod, "CoInitialize", lambda: None, raising=False)

    audio = mod.AudioController()
    rows = audio.list_audio_devices()

    assert [row["name"] for row in rows] == [
        "扬声器 (USB Audio)",
        "Realtek HD Audio 2nd output (Realtek(R) Audio)",
    ]
    assert rows[0]["is_default"] is True
    assert rows[0]["is_target_match"] is False
    assert rows[0]["is_fallback_match"] is False
    assert rows[1]["is_default"] is False
    assert rows[1]["is_target_match"] is False
    assert rows[1]["is_fallback_match"] is False


def test_audio_controller_bind_device_by_index_switches_endpoint(monkeypatch):
    mod = load_module()

    class FakeDevice:
        def __init__(self, dev_id, name):
            self.id = dev_id
            self.FriendlyName = name
            self.EndpointVolume = object()

    default = FakeDevice("dev-default", "扬声器 (USB Audio)")
    hdmi = FakeDevice("dev-hdmi", "显示器 (NVIDIA High Definition Audio)")
    realtek = FakeDevice("dev-realtek", "Realtek HD Audio 2nd output (Realtek(R) Audio)")
    devices = [default, hdmi, realtek]

    class FakeAudioUtilities:
        @staticmethod
        def GetSpeakers():
            return default

        @staticmethod
        def GetAllDevices():
            return devices

    monkeypatch.setattr(mod, "_HAS_PYCAW", True)
    monkeypatch.setattr(mod, "AudioUtilities", FakeAudioUtilities, raising=False)
    monkeypatch.setattr(mod, "CoInitialize", lambda: None, raising=False)

    audio = mod.AudioController()
    selected = audio.bind_device_by_index(1)

    assert selected["id"] == "dev-hdmi"
    assert selected["name"] == "显示器 (NVIDIA High Definition Audio)"
    assert audio._last_dev_id == "dev-hdmi"
    assert audio._vol_iface is hdmi.EndpointVolume
