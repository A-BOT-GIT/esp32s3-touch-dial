# ESP32-S3 Touch Dial 当前项目状态

日期：2026-07-08  
分支：`debug/ble-hwcdc-reconnect`

## 1. 当前结论

当前固件已经完成基础 BLE HID Dial 链路打通，并在 Windows 端实测通过以下能力：

- 可以稳定配对并连接为 `ESP32-S3 Radial MVP`
- 可以唤起 Windows Radial 菜单
- 可以在 `ESP32 Radial Probe` 中稳定收到：
  - `RotationChanged`
  - `ButtonPressed`
  - `ButtonReleased`
  - `ButtonClicked`

最新实测日志：

```text
[00:00:29.236] RotationChanged delta=10.00 total=10.00
[00:00:30.657] RotationChanged delta=-10.00 total=0.00
[00:00:32.232] ButtonPressed
[00:00:32.232] ButtonReleased
[00:00:32.232] ButtonClicked count=1
```

## 2. 当前固件关键状态

- HID Input Report 已从旧版 2 字节格式改为 3 字节格式：
  - byte0: button
  - byte1-2: signed 16-bit dial delta
- 当前旋转步进：`10.0° / detent`
  - 代码常量：`RADIAL_DETENT_TENTHS_DEG = 100`
- 已增加 BLE 诊断 GATT 服务：
  - service `6B1D0001-7E57-4A5A-8C6C-5F3E2B917101`
  - char `6B1D0002-7E57-4A5A-8C6C-5F3E2B917101`
- 已增加运行时诊断命令：
  - `DIAG ALL ON/OFF`
  - `DIAG STATUS`
  - `DIAG GATT STATUS`
  - `DIAG NOTIFY TEST`
  - `RADIAL TEST CW/CCW/DOWN/UP/TAP/HOLD`
  - `LOG QUIET/VERBOSE`

## 3. Linux 侧烧写与验证

统一入口：

```bash
tools/deploy_linux.sh
```

当前脚本能力：

- 编译 Arduino 固件
- 全量烧写：
  - bootloader
  - partitions
  - `boot_app0.bin`
  - `app0`
  - `app1`
- 优先通过 `ttyACM1` 的 CH343P DTR 脉冲启动固件
- 如控制口无响应，可回退到 `ttyACM0` watchdog reset
- 在 probe 前自动等待 `ttyACM1` 重新出现，避免因 USB 重新枚举慢而误报失败
- 自动发送：
  - `LOG QUIET`
  - `BLE STATUS`
  - `HID STATUS`

常用命令：

```bash
rtk bash /home/zza/projects/esp32s3_touch_dial/tools/deploy_linux.sh
rtk bash /home/zza/projects/esp32s3_touch_dial/tools/deploy_linux.sh --skip-compile
rtk bash /home/zza/projects/esp32s3_touch_dial/tools/deploy_linux.sh --skip-flash --skip-start
```

## 4. 端口说明

Linux 侧当前默认端口分工：

- `/dev/ttyACM0`
  - ESP32-S3 ROM bootloader / 烧录口
  - `esptool` 主要使用这个口
- `/dev/ttyACM1`
  - 固件控制与日志口
  - 用于发送 `LOG QUIET`、`HID STATUS`、`RADIAL TEST CW` 等命令

注意：

- 脚本末尾历史上最常见的假失败原因，不是烧录失败，而是 `ttyACM1` 重新枚举慢
- 当前 `deploy_linux.sh` 已加入等待逻辑，但如果主机 USB 状态异常，仍应优先手动确认 `/dev/ttyACM1` 是否已回来

## 5. Windows 侧注意事项

### 5.1 已确认可用

- `ESP32 Radial Probe` 中的自定义 RadialController 事件接收是可用的
- 旋转和短按事件已经通过

### 5.2 当前已确认不可依赖

Windows 默认 Radial 菜单中的系统工具项：

- `滚动`
- `缩放`

在实测中即使菜单可见，也未能在 Edge/Chrome 页面或图片查看器中产生预期效果。

因此当前结论是：

- 设备已被 Windows 识别为 Radial Controller
- 但 Windows 默认系统工具映射不可作为项目可交付能力依赖

后续若要实现“稳定滚动 / 缩放”，建议走 Windows 端自定义映射层，而不是继续依赖系统默认菜单项。

## 6. 推荐验证流程

### Linux

1. 烧写并启动：

```bash
rtk bash /home/zza/projects/esp32s3_touch_dial/tools/deploy_linux.sh
```

2. 手动发送测试命令：

```text
LOG QUIET
RADIAL TEST CW
RADIAL TEST CCW
RADIAL TEST TAP
HID STATUS
```

### Windows

1. 打开 `ESP32 Radial Probe`
2. 长按呼出菜单，选中 `ESP32 Probe`
3. 验证：
   - 旋转产生 `RotationChanged delta=10.00`
   - 短按产生 `ButtonPressed / ButtonReleased / ButtonClicked`

## 7. 当前下一步建议

当前不建议继续在“系统默认滚动 / 缩放”上投入排查时间。  
更合理的下一目标是：

1. 保持当前固件不大改
2. Windows 端实现自定义映射层
3. 将：
   - `RotationChanged` 映射为真实滚轮
   - 按住或模式切换后的旋转映射为缩放

## 8. 本次应一并保存的关键文件

- `esp32s3_touch_dial.ino`
- `tools/deploy_linux.sh`
- `tools/diag_test.py`
- `tools/win_raw_hid_probe/hid_probe.py`
- `tools/win_raw_hid_probe/raw_hid_listener_cn.py`
- `tools/win_raw_hid_probe/README.md`
- 本文档
