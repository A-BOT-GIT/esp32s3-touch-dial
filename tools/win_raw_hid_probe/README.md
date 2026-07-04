# Windows Raw HID Probe

直接枚举 Windows HID 设备，读取 ESP32-S3 Radial MVP 的 BLE HID Input Report。

**不需要** RadialController API，**不依赖** 系统 Radial 菜单。

## 安装

```cmd
pip install hidapi
```

Windows 可能需要额外安装 hidapi DLL。从 [Releases](https://github.com/libusb/hidapi/releases) 下载
对应的 `hidapi-win.zip`，把 DLL 放到 Python 目录或系统 `PATH`。

## 使用

### 1. 列出 HID 设备

```cmd
python tools\win_raw_hid_probe\hid_probe.py list
```

ESP32 相关设备会标记得分最高。记下设备路径或 VID/PID。

### 2. 监听输入报告

```cmd
python tools\win_raw_hid_probe\hid_probe.py listen --name "ESP32" --timeout 120
```

或指定路径：

```cmd
python tools\win_raw_hid_probe\hid_probe.py listen --path "\\?\HID#..." --timeout 120
```

### 3. 操作 ESP32

监听启动后，旋转和按压编码器。应看到类似输出：

```
[16:55:01.123] #0001 len=2  02 00
               button=0 dial=+1  (raw=0x0002)
[16:55:02.456] #0002 len=2  FE FF
               button=0 dial=-1  (raw=0xFFFE)
[16:55:03.789] #0003 len=2  01 00
               button=1 dial=+0  (raw=0x0001)
[16:55:04.111] #0004 len=2  00 00
               button=0 dial=+0  (raw=0x0000)
```

### 预期 report

| ESP32 操作 | 期望 bytes |
|-----------|-----------|
| 旋转右 (+15) | `1E 00` |
| 旋转左 (-15) | `E2 FF` |
| 按下 | `01 00` |
| 释放 | `00 00` |
| 按下+右转 | `1F 00` |
| 按下+左转 | `E3 FF` |

## 常见问题

### 找不到设备

- 确认 ESP32-S3 已蓝牙配对并连接
- 以**管理员**权限运行
- 关闭其他 HID 工具（Arduino Serial Monitor 等）
- 先运行 `list` 命令查看所有设备

### PermissionError / 无法打开设备

- 以管理员运行 CMD/PowerShell
- 某些 BLE HID 设备需要 Exclusive Access，关闭其他读取该设备的程序

### 收到空报告

- 这是正常现象——BLE HID 库在无数据时返回空
- 旋转/按压编码器时应有数据
