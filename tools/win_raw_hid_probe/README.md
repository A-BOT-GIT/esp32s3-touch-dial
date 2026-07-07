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

### 中文入口

推荐优先使用仓库内的中文入口：

```cmd
python tools\win_raw_hid_probe\raw_hid_listener_cn.py list
python tools\win_raw_hid_probe\raw_hid_listener_cn.py listen
```

默认行为：

- `list`：列出并打分所有 HID 设备，优先标记疑似 `ESP32-S3 Radial MVP`
- `listen`：默认按名称 `ESP32` 搜索并监听

如需精确指定：

```cmd
python tools\win_raw_hid_probe\raw_hid_listener_cn.py listen --path "\\?\HID#..."
python tools\win_raw_hid_probe\raw_hid_listener_cn.py listen --vid 303A --pid 1001
```

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
[00:00:29.236] #0001 len=3  00 64 00
               button=0 dial=+100 (+10.0 deg)  (raw=00 64 00)
[00:00:30.657] #0002 len=3  00 9C FF
               button=0 dial=-100 (-10.0 deg)  (raw=00 9C FF)
[00:00:32.232] #0003 len=3  01 00 00
               button=1 dial=+0 (+0.0 deg)  (raw=01 00 00)
[00:00:32.240] #0004 len=3  00 00 00
               button=0 dial=+0 (+0.0 deg)  (raw=00 00 00)
```

### 预期 report

| ESP32 操作 | 期望 bytes |
|-----------|-----------|
| 旋转右 (+10.0 deg) | `00 64 00` |
| 旋转左 (-10.0 deg) | `00 9C FF` |
| 按下 | `01 00 00` |
| 释放 | `00 00 00` |
| 按下+右转 | `01 64 00` |
| 按下+左转 | `01 9C FF` |

说明：

- 当前固件 HID Input Report 已调整为 3 字节格式：
  - byte0: button
  - byte1-2: signed 16-bit dial delta (0.1 degree units)
- 当前调校值为每步 `10.0°`，所以单步旋转对应 `+100 / -100`

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
