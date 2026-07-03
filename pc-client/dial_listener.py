"""
ESP8266 Dial Listener — 双模式接收版（带托盘图标）

- SerialReader 线程：扫描 COM 口 → 打开串口 → 回 ACK → 解析 >EVENT
- UDPReader 线程：监听 UDP 8888 → 解析 JSON action
- 两者共享 KEY_MAP 动作映射，行为一致
- 主线程运行 pystray 托盘图标（右键菜单 / 动态状态色）
- 无黑窗口后台运行（配合 pyinstaller --noconsole 打包）
"""

import argparse
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pynput.keyboard import Key, Controller

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None  # pyserial 未安装则只走 UDP

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = None
    ImageDraw = None

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume, IMMDeviceEnumerator, EDataFlow, ERole, AudioDevice
    from comtypes import CLSCTX_ALL, CoCreateInstance, CLSCTX_INPROC_SERVER, CoInitialize
    _HAS_PYCAW = True
except ImportError:
    CoInitialize = None
    _HAS_PYCAW = False

# ── Windows 控制台 QuickEdit 禁用（仅限打包后的控制台模式） ──
# 直接在 PowerShell / CMD 里运行脚本时，不要改控制台模式，否则会导致
# 无法正常框选文本，且终端交互体验变差。
IS_FROZEN = bool(getattr(sys, "frozen", False))

if sys.platform == "win32" and IS_FROZEN and sys.stdout is not None and sys.stdout.isatty():
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(h, ctypes.byref(mode))
        kernel32.SetConsoleMode(h, (mode.value & ~0x0040) | 0x0080)
    except Exception:
        pass


# ── 日志：写文件，避免 --noconsole 下的 stdout 异常 ───────
def _log_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.path.expanduser("~/.local/share")
    d = Path(base) / "dial"
    d.mkdir(parents=True, exist_ok=True)
    return d


_log_initialized = False


def _setup_logging():
    global _log_initialized
    if _log_initialized:
        return
    _log_initialized = True

    log_file = _log_dir() / "dial.log"
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # 有 tty 时也回显到控制台
    if sys.stdout is not None and sys.stdout.isatty():
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("[%(asctime)s] %(message)s"))
        root.addHandler(ch)


log = logging.getLogger("dial")


# ── 按键映射 ────────────────────────────────────────────
KEY_MAP = {
    "left":      (Key.media_volume_down, "音量减小"),
    "right":     (Key.media_volume_up,   "音量增大"),
    "press":     (Key.media_play_pause,  "播放/暂停"),
    "longpress": (None,                   "Win+D 回到桌面"),
}

UDP_IP   = "0.0.0.0"
UDP_PORT = 8888


# ── 全局状态（给托盘图标用） ───────────────────────────
class State:
    """线程安全的设备状态快照"""

    MODE_DISCONNECTED = "未连接"
    MODE_WIRED        = "有线"
    MODE_WIRELESS     = "无线"

    def __init__(self):
        self._lock = threading.Lock()
        self.mode = State.MODE_DISCONNECTED
        self.last_event = "—"
        self.last_event_time = 0.0
        self.event_count = 0
        self.tray_icon = None   # 由 main 注入

    def set_mode(self, mode: str):
        with self._lock:
            if self.mode == mode:
                return
            self.mode = mode
        log.info("状态变更: %s", mode)
        # 模式变更：重绘图标 + 更新菜单
        self._refresh_icon()
        self._refresh_menu()

    def record_event(self, action: str):
        with self._lock:
            self.last_event = action
            self.last_event_time = time.time()
            self.event_count += 1
        # 事件只更新菜单文本，不重绘图标（避免高频旋转时 UI 拥塞）
        self._refresh_menu()

    def snapshot(self):
        with self._lock:
            return (self.mode, self.last_event, self.event_count)

    def _refresh_icon(self):
        if self.tray_icon is None:
            return
        try:
            self.tray_icon.icon = _make_icon_image(self.mode)
            self.tray_icon.title = f"ESP8266 Dial — {self.mode}"
        except Exception as e:
            log.debug("刷新托盘图标失败: %s", e)

    def _refresh_menu(self):
        if self.tray_icon is None:
            return
        try:
            if hasattr(self.tray_icon, "update_menu"):
                self.tray_icon.update_menu()
        except Exception as e:
            log.debug("刷新托盘菜单失败: %s", e)


STATE = State()


# ── 音频控制（pycaw → 自动优先绑定指定扬声器） ────────────
VOLUME_STEP = 2  # 每次旋转调节 2%（/100 单位）
PRIMARY_TARGET_AUDIO_NAME = "扬声器 (Realtek(R) Audio)"
FALLBACK_TARGET_AUDIO_NAME = "扬声器 (7.1 Surround Sound)"

class AudioController:
    """封装 pycaw：直接读写 Windows 当前默认音频设备的主音量。"""

    def __init__(self):
        self._vol_iface = None
        self._last_dev_id = None
        self._last_check_time = 0.0
        self._com_initialized = False
        self._manual_device_id = None

    def _ensure_com_initialized(self):
        """Initialize COM on the current thread before calling pycaw/comtypes."""
        if self._com_initialized:
            return
        if CoInitialize is None:
            return
        CoInitialize()
        self._com_initialized = True

    def _target_names(self):
        primary = PRIMARY_TARGET_AUDIO_NAME.strip().lower()
        fallback = FALLBACK_TARGET_AUDIO_NAME.strip().lower()
        return primary, fallback

    def _enumerate_audio_devices(self):
        if not _HAS_PYCAW:
            return []

        self._ensure_com_initialized()
        default_device = AudioUtilities.GetSpeakers()
        candidates = []
        if default_device is not None:
            candidates.append(default_device)

        get_all = getattr(AudioUtilities, "GetAllDevices", None)
        if callable(get_all):
            try:
                for dev in get_all() or []:
                    if dev is not None:
                        candidates.append(dev)
            except Exception as e:
                log.debug("枚举音频设备失败，退回默认设备: %s", e)

        rows = []
        seen = set()
        primary_target, fallback_target = self._target_names()
        default_id = getattr(default_device, "id", None)
        for dev in candidates:
            dev_id = getattr(dev, "id", None)
            if dev_id in seen:
                continue
            seen.add(dev_id)
            name = str(getattr(dev, "FriendlyName", "") or "")
            lower_name = name.lower()
            rows.append({
                "index": len(rows),
                "id": dev_id,
                "name": name,
                "is_default": dev_id == default_id,
                "is_target_match": lower_name == primary_target,
                "is_fallback_match": lower_name == fallback_target,
                "is_manual_selected": dev_id == self._manual_device_id,
                "_device": dev,
            })
        return rows

    def list_audio_devices(self):
        rows = self._enumerate_audio_devices()
        return [
            {
                "index": row["index"],
                "id": row["id"],
                "name": row["name"],
                "is_default": row["is_default"],
                "is_target_match": row["is_target_match"],
                "is_fallback_match": row["is_fallback_match"],
                "is_manual_selected": row["is_manual_selected"],
            }
            for row in rows
        ]

    def _bind_device(self, dev, *, source: str):
        self._vol_iface = dev.EndpointVolume
        self._last_dev_id = getattr(dev, "id", None)
        self._last_check_time = time.time()
        log.info("绑定音频控制到%s设备: %s", source, getattr(dev, "FriendlyName", ""))
        return {
            "id": self._last_dev_id,
            "name": str(getattr(dev, "FriendlyName", "") or ""),
        }

    def bind_device_by_index(self, index: int):
        rows = self._enumerate_audio_devices()
        if not rows:
            raise RuntimeError("当前没有可用的音频设备")
        if index < 0 or index >= len(rows):
            raise IndexError(f"音频设备索引越界: {index}")
        row = rows[index]
        self._manual_device_id = row["id"]
        selected = self._bind_device(row["_device"], source="手动选择")
        selected["index"] = row["index"]
        return selected

    def clear_manual_binding(self):
        self._manual_device_id = None
        self._vol_iface = None
        self._last_dev_id = None
        self._last_check_time = 0.0

    def _select_target_device(self, default_device):
        """自动模式：只绑定指定名称的音频端点；找不到则拒绝绑定其他设备。"""
        rows = self._enumerate_audio_devices()
        if self._manual_device_id is not None:
            for row in rows:
                if row["id"] == self._manual_device_id:
                    return row["_device"]
            log.warning("手动绑定的音频设备已不存在: %s", self._manual_device_id)
            self.clear_manual_binding()
            return None

        primary_target, fallback_target = self._target_names()
        if not primary_target and not fallback_target:
            return default_device

        for row in rows:
            if row["is_target_match"]:
                return row["_device"]
        for row in rows:
            if row["is_fallback_match"]:
                return row["_device"]
        return None

    def _ensure_active_device(self):
        """
        检查并确保绑定到当前的默认音频输出设备。
        由于设备切换可能发生，我们加上节流：如果在 1.5 秒内发生过连续旋转，就复用当前接口，不重复查询。
        """
        if not _HAS_PYCAW:
            return False

        now = time.time()
        if self._vol_iface is not None and (now - self._last_check_time) < 1.5:
            self._last_check_time = now
            return True

        try:
            self._ensure_com_initialized()
            default_device = AudioUtilities.GetSpeakers()
            dev = self._select_target_device(default_device)
            if dev is None:
                if self._manual_device_id is not None:
                    log.warning("未找到手动选择的音频设备")
                else:
                    log.warning(
                        "未找到目标音频设备: %s；备用托底也未找到: %s",
                        PRIMARY_TARGET_AUDIO_NAME,
                        FALLBACK_TARGET_AUDIO_NAME,
                    )
                self._vol_iface = None
                self._last_dev_id = None
                return False

            cur_dev_id = dev.id
            if self._vol_iface is None or cur_dev_id != self._last_dev_id:
                source = "手动选择的" if self._manual_device_id is not None else "当前默认"
                self._bind_device(dev, source=source)

            self._last_check_time = now
            return True
        except Exception as e:
            log.warning("获取或激活默认音频设备失败: %s", e)
            self._vol_iface = None
            self._last_dev_id = None
            return False

    def change_volume(self, delta: int):
        """delta 正数=增大，负数=减小，单位为百分点"""
        if not self._ensure_active_device():
            return False

        try:
            vol = self._vol_iface.GetMasterVolumeLevelScalar()
            new = max(0.0, min(1.0, vol + delta / 100.0))
            self._vol_iface.SetMasterVolumeLevelScalar(new, None)
            return True
        except Exception:
            self._vol_iface = None  # 出错后清空，下次重试
            return False

    def set_volume_percent(self, value: int):
        """直接把当前默认输出设备主音量设置为 0~100 的绝对百分比。"""
        if not self._ensure_active_device():
            return False

        try:
            clamped = max(0, min(100, int(value)))
            self._vol_iface.SetMasterVolumeLevelScalar(clamped / 100.0, None)
            return True
        except Exception:
            self._vol_iface = None
            return False

    def mute_toggle(self):
        if not self._ensure_active_device():
            return False

        try:
            cur = self._vol_iface.GetMute()
            self._vol_iface.SetMute(not cur, None)
            return True
        except Exception:
            self._vol_iface = None
            return False


# ── 动作执行 ────────────────────────────────────────────
class ActionRunner:
    def __init__(self):
        self.keyboard = Controller()
        self.audio = AudioController()
        self._lock = threading.Lock()

    def run(self, action: str, source: str):
        with self._lock:
            try:
                if action == "mute_toggle":
                    if self.audio.mute_toggle():
                        log.info("[%s] mute_toggle → 静音/取消静音", source)
                        STATE.record_event("mute_toggle")
                        return
                    log.warning("[%s] mute_toggle 执行失败", source)
                    return

                if action == "longpress":
                    log.info("[%s] longpress → Win+D 回到桌面", source)
                    self._win_d()
                    STATE.record_event("longpress")
                    return

                # 音量改用 pycaw 直接操作当前默认设备
                if action == "left" and _HAS_PYCAW:
                    if self.audio.change_volume(-VOLUME_STEP):
                        log.info("[%s] left → 音量减小 (pycaw)", source)
                        STATE.record_event(action)
                        return
                if action == "right" and _HAS_PYCAW:
                    if self.audio.change_volume(+VOLUME_STEP):
                        log.info("[%s] right → 音量增大 (pycaw)", source)
                        STATE.record_event(action)
                        return

                # fallback：pycaw 不可用时走媒体键（原行为）
                if action in KEY_MAP:
                    key, desc = KEY_MAP[action]
                    log.info("[%s] %s → %s", source, action, desc)
                    if key is not None:
                        self.keyboard.press(key)
                        self.keyboard.release(key)
                    STATE.record_event(action)
                else:
                    log.warning("[%s] 未知动作: %s", source, action)
            except Exception as e:
                log.error("[%s] 动作执行失败: %s", source, e)

    def run_volume(self, value: int, source: str):
        with self._lock:
            try:
                clamped = max(0, min(100, int(value)))
                if self.audio.set_volume_percent(clamped):
                    log.info("[%s] volume → %d%%", source, clamped)
                    STATE.record_event(f"volume={clamped}")
                else:
                    log.warning("[%s] volume=%d 设置失败", source, clamped)
            except Exception as e:
                log.error("[%s] 音量设置失败: %s", source, e)

    def _win_d(self):
        self.keyboard.press(Key.cmd_l)
        self.keyboard.press("d")
        self.keyboard.release("d")
        self.keyboard.release(Key.cmd_l)


# ── 串口接收 ────────────────────────────────────────────
class SerialReader(threading.Thread):
    PORT_HINTS = (
        "CH340", "CH341", "CP210", "FTDI", "USB-SERIAL", "wchusbserial",
        "ESP32", "ESPRESSIF", "USB Serial Device", "USB Single Serial",
        "USB JTAG/serial", "USB JTAG/Serial", "ACM",
    )

    RE_RIGHT = re.compile(r"^>RIGHT\s+pos=(-?\d+)")
    RE_LEFT  = re.compile(r"^>LEFT\s+pos=(-?\d+)")
    RE_PRESS = re.compile(r"^>PRESS(?:\s+#(\d+))?$")
    RE_LONG  = re.compile(r"^>LONG\s+(\d+)")
    RE_VOLUME = re.compile(r"^>VOLUME\s+(-?\d+)")

    def __init__(self, runner: ActionRunner):
        super().__init__(daemon=True, name="serial")
        self.runner = runner
        self._stop_event = threading.Event()
        self._ser = None

    def stop(self):
        self._stop_event.set()

    def run(self):
        if serial is None:
            log.warning("pyserial 未安装，串口功能禁用")
            return

        log.info("开始扫描 ESP8266 串口...")
        scan_count = 0
        while not self._stop_event.is_set():
            port = self._find_port()
            if port is None:
                scan_count += 1
                if scan_count % 15 == 1:
                    log.info("未检测到 ESP8266 串口，继续扫描...")
                self._stop_event.wait(2.0)
                continue
            scan_count = 0

            try:
                log.info("尝试打开串口 %s", port)
                self._ser = serial.Serial(
                    port=port,
                    baudrate=115200,
                    timeout=None,
                    write_timeout=1.0,
                )
                # ESP32-S3 TinyUSB CDC on this board stays silent unless DTR is asserted.
                # Keep RTS deasserted to avoid accidental reset/bootloader transitions.
                self._ser.dtr = True
                self._ser.rts = False
                log.info("串口已连接 %s (DTR=%s RTS=%s)", port, self._ser.dtr, self._ser.rts)
                # 连上串口但模式未知，等到收到 >MODE 再更新
                self._read_loop()
            except serial.SerialException as e:
                log.info("串口 %s 异常: %s", port, e)
            except Exception as e:
                log.error("串口意外错误: %s", e)
            finally:
                if self._ser:
                    try:
                        self._ser.close()
                    except Exception:
                        pass
                    self._ser = None
                log.info("串口已关闭，2 秒后重新扫描")
                # 失去有线连接，但 UDP 还能收 → 如果处于 WIRED 就降级到 DISCONNECTED
                if STATE.mode == State.MODE_WIRED:
                    STATE.set_mode(State.MODE_DISCONNECTED)
                self._stop_event.wait(2.0)

    ESPRESSIF_VIDS = {0x303A, 0x10C4, 0x1A86}

    def _port_score(self, port) -> int:
        desc = " ".join(
            str(x or "")
            for x in (
                getattr(port, "description", ""),
                getattr(port, "manufacturer", ""),
                getattr(port, "hwid", ""),
            )
        ).lower()
        vid = getattr(port, "vid", None)
        pid = getattr(port, "pid", None)

        score = 0

        # 最优先：ESP32-S3 native USB CDC / JTAG+CDC。它的 COM 号会变，但 303A:1001 不变。
        if vid == 0x303A and pid == 0x1001:
            score += 100
        if "vid:pid=303a:1001" in desc or "vid_303a&pid_1001" in desc:
            score += 100
        if "espressif" in desc:
            score += 30
        if "usb jtag/serial" in desc or "usb jtag/serial debug unit" in desc:
            score += 30
        if "esp32" in desc or "esp32-s3" in desc:
            score += 20
        if "acm" in desc:
            score += 10

        # 回退：桥口 / 常见 USB UART 芯片。
        if vid == 0x1A86 and pid == 0x55D3:
            score += 20
        if vid == 0x10C4:
            score += 15
        if any(hint.lower() in desc for hint in self.PORT_HINTS):
            score += 10
        if "vid:pid=10c4:" in desc or "vid:pid=1a86:" in desc:
            score += 10

        # 最弱兜底。
        if "usb" in desc or "serial" in desc:
            score += 1

        return score

    def _is_supported_port(self, port) -> bool:
        return self._port_score(port) > 0

    def _find_port(self):
        manual_port = os.environ.get("DIAL_SERIAL_PORT")
        if manual_port:
            log.info("使用手动指定串口: %s", manual_port)
            return manual_port

        try:
            best_port = None
            best_score = 0
            for p in serial.tools.list_ports.comports():
                score = self._port_score(p)
                if score <= 0:
                    continue
                log.info(
                    "检测到候选串口: %s score=%s desc=%s manufacturer=%s hwid=%s vid=%s pid=%s",
                    getattr(p, "device", "?"),
                    score,
                    getattr(p, "description", None),
                    getattr(p, "manufacturer", None),
                    getattr(p, "hwid", None),
                    getattr(p, "vid", None),
                    getattr(p, "pid", None),
                )
                if score > best_score:
                    best_port = p
                    best_score = score
            if best_port is not None:
                return best_port.device
        except Exception as e:
            log.error("扫描串口失败: %s", e)
        return None

    def _read_loop(self):
        ser = self._ser
        assert ser is not None
        buf = b""
        MAX_BUF = 8192  # 防止对端狂发无 \n 的垃圾导致内存膨胀
        while not self._stop_event.is_set():
            try:
                chunk = ser.read(1)
            except serial.SerialException:
                raise
            if not chunk:
                continue
            buf += chunk
            if ser.in_waiting:
                buf += ser.read(ser.in_waiting)

            if len(buf) > MAX_BUF:
                log.warning("串口缓冲溢出（%d 字节），丢弃", len(buf))
                buf = b""
                continue

            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip(b"\r\x00").decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                self._handle_line(line)

    def _handle_line(self, line: str):
        if line.startswith(">HELLO") or line.startswith(">PING"):
            try:
                self._ser.write(b"ACK\n")
            except Exception as e:
                log.error("ACK 写入失败: %s", e)
            return

        if line.startswith(">MODE"):
            log.info("设备切换: %s", line)
            if "wired" in line:
                STATE.set_mode(State.MODE_WIRED)
            elif "wireless" in line:
                STATE.set_mode(State.MODE_WIRELESS)
            return

        if line.startswith(">STATUS") or line.startswith(">BOOT"):
            return

        m = self.RE_VOLUME.match(line)
        if m:
            self.runner.run_volume(int(m.group(1)), "serial")
        elif line.startswith(">MUTE_TOGGLE"):
            self.runner.run("mute_toggle", "serial")
        elif self.RE_RIGHT.match(line):
            self.runner.run("right", "serial")
        elif self.RE_LEFT.match(line):
            self.runner.run("left", "serial")
        elif self.RE_PRESS.match(line):
            self.runner.run("press", "serial")
        elif self.RE_LONG.match(line):
            self.runner.run("longpress", "serial")
        elif line.startswith(">DOWN") or line.startswith(">UP") or line.startswith(">HOLD"):
            pass
        else:
            log.debug("未解析行: %s", line)


# ── UDP 接收 ────────────────────────────────────────────
class UDPReader(threading.Thread):
    def __init__(self, runner: ActionRunner):
        super().__init__(daemon=True, name="udp")
        self.runner = runner
        self._stop_event = threading.Event()
        self._sock = None

    def stop(self):
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass

    def run(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self._sock.bind((UDP_IP, UDP_PORT))
        except OSError as e:
            log.error("UDP 端口 %d 绑定失败: %s", UDP_PORT, e)
            return

        self._sock.settimeout(None)
        log.info("UDP 监听 %d", UDP_PORT)

        while not self._stop_event.is_set():
            try:
                data, addr = self._sock.recvfrom(1024)
            except OSError:
                break
            except Exception as e:
                log.error("UDP 接收错误: %s", e)
                continue

            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                log.warning("UDP JSON 解析失败: %r", data)
                continue

            action = payload.get("action", "")
            if action:
                # UDP 收到事件 → 当前一定是 WIRELESS 模式
                if STATE.mode != State.MODE_WIRELESS:
                    STATE.set_mode(State.MODE_WIRELESS)
                self.runner.run(action, f"udp:{addr[0]}")


# ── 托盘图标 ────────────────────────────────────────────
_MODE_COLOR = {
    State.MODE_DISCONNECTED: (136, 136, 136),  # 灰
    State.MODE_WIRED:        (0,   170, 0),    # 绿
    State.MODE_WIRELESS:     (0,   102, 255),  # 蓝
}


def _make_icon_image(mode: str):
    """生成一张 64x64 的单色圆形图标"""
    if Image is None:
        return None
    color = _MODE_COLOR.get(mode, (136, 136, 136))
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=color + (255,), outline=(255, 255, 255, 230), width=3)
    # 中心画 D
    try:
        from PIL import ImageFont
        # PIL 默认字体可能不够大，用 load_default 就行
        font = ImageFont.load_default()
        draw.text((22, 18), "D", fill=(255, 255, 255, 255), font=font)
    except Exception:
        pass
    return img


def _open_log_file(icon=None, item=None):
    """右键菜单：打开日志文件"""
    path = str(_log_dir() / "dial.log")
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        log.error("打开日志失败: %s", e)


def _open_log_dir(icon=None, item=None):
    """右键菜单：打开日志目录"""
    path = str(_log_dir())
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        log.error("打开日志目录失败: %s", e)


def _quit_app(icon, item=None):
    log.info("用户通过托盘退出")
    icon.visible = False
    icon.stop()


def _build_tray_icon():
    """构造托盘图标（需要在主线程调用 icon.run()）"""
    if pystray is None:
        log.warning("pystray 未安装，托盘图标禁用")
        return None

    def _mode_label(_item=None):
        mode, last, count = STATE.snapshot()
        return f"模式: {mode}"

    def _event_label(_item=None):
        _, last, count = STATE.snapshot()
        if count == 0:
            return "最近事件: —"
        return f"最近: {last}  (#{count})"

    menu = pystray.Menu(
        pystray.MenuItem(_mode_label, None, enabled=False),
        pystray.MenuItem(_event_label, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("打开日志文件", _open_log_file),
        pystray.MenuItem("打开日志目录", _open_log_dir),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _quit_app),
    )

    icon = pystray.Icon(
        "dial_listener",
        icon=_make_icon_image(STATE.mode),
        title="ESP8266 Dial — 未连接",
        menu=menu,
    )
    return icon


def _print_audio_devices(audio: AudioController):
    rows = audio.list_audio_devices()
    if not rows:
        print("未检测到可用音频设备。")
        return rows

    print("\n当前音频设备列表:")
    for row in rows:
        tags = []
        if row["is_default"]:
            tags.append("default")
        if row["is_target_match"]:
            tags.append("target")
        if row["is_fallback_match"]:
            tags.append("fallback")
        if row["is_manual_selected"]:
            tags.append("manual")
        suffix = f" [{' '.join(tags)}]" if tags else ""
        print(f"  {row['index']}: {row['name']}{suffix}")
    print()
    return rows


def run_audio_debug_cli():
    _setup_logging()
    audio = AudioController()

    print("音频调试模式")
    print("命令: list | bind <index> | auto | vol <0-100> | up [n] | down [n] | mute | current | quit")
    _print_audio_devices(audio)

    while True:
        try:
            raw = input("audio-debug> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].lower()
        args = parts[1:]

        try:
            if cmd in {"quit", "exit", "q"}:
                break
            if cmd in {"list", "ls"}:
                _print_audio_devices(audio)
                continue
            if cmd == "bind":
                if len(args) != 1:
                    print("用法: bind <index>")
                    continue
                row = audio.bind_device_by_index(int(args[0]))
                print(f"已手动绑定: {row['index']} - {row['name']}")
                continue
            if cmd == "auto":
                audio.clear_manual_binding()
                print("已切回自动匹配模式。")
                continue
            if cmd == "current":
                rows = _print_audio_devices(audio)
                current = next((r for r in rows if r["is_manual_selected"]), None)
                if current is not None:
                    print(f"当前手动绑定: {current['index']} - {current['name']}")
                else:
                    print("当前为自动匹配模式。")
                continue
            if cmd == "vol":
                if len(args) != 1:
                    print("用法: vol <0-100>")
                    continue
                value = int(args[0])
                ok = audio.set_volume_percent(value)
                print(f"设置音量到 {max(0, min(100, value))}%: {'OK' if ok else 'FAIL'}")
                continue
            if cmd == "up":
                step = int(args[0]) if args else 2
                ok = audio.change_volume(abs(step))
                print(f"音量增加 {abs(step)}%: {'OK' if ok else 'FAIL'}")
                continue
            if cmd == "down":
                step = int(args[0]) if args else 2
                ok = audio.change_volume(-abs(step))
                print(f"音量减少 {abs(step)}%: {'OK' if ok else 'FAIL'}")
                continue
            if cmd == "mute":
                ok = audio.mute_toggle()
                print(f"静音切换: {'OK' if ok else 'FAIL'}")
                continue
            print("未知命令。可用命令: list, bind, auto, vol, up, down, mute, current, quit")
        except Exception as e:
            print(f"命令执行失败: {e}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="ESP32/ESP8266 Dial PC Listener")
    parser.add_argument("--audio-debug", action="store_true", help="进入音频设备调试模式，可手动枚举/绑定/调音量")
    return parser.parse_args(argv)


# ── 主入口 ──────────────────────────────────────────────
def main(argv=None):
    args = parse_args(argv)
    if args.audio_debug:
        run_audio_debug_cli()
        return

    _setup_logging()

    log.info("=" * 40)
    log.info("ESP8266 Dial Listener 启动")
    log.info("日志文件: %s", _log_dir() / "dial.log")
    log.info("按键映射:")
    for a, (_, d) in KEY_MAP.items():
        log.info("  %-10s → %s", a, d)

    runner = ActionRunner()
    sr = SerialReader(runner)
    ur = UDPReader(runner)

    sr.start()
    ur.start()

    icon = _build_tray_icon() if IS_FROZEN else None
    STATE.tray_icon = icon

    if icon is not None:
        def _sig_handler(sig, _frame):
            log.info("收到信号 %s，触发退出", sig)
            try:
                icon.stop()
            except Exception:
                pass

        try:
            signal.signal(signal.SIGINT, _sig_handler)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, _sig_handler)
        except Exception as e:
            log.debug("注册信号处理器失败（非主线程?）: %s", e)

        try:
            icon.run()
        except KeyboardInterrupt:
            log.info("收到 Ctrl+C（fallback）")
    else:
        try:
            while sr.is_alive() or ur.is_alive():
                time.sleep(1.0)
        except KeyboardInterrupt:
            log.info("收到 Ctrl+C")

    log.info("正在退出...")
    sr.stop()
    ur.stop()
    sr.join(timeout=2)
    ur.join(timeout=2)
    log.info("已退出")


if __name__ == "__main__":
    main()
