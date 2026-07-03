# ESP32-S3 Touch Dial

当前项目已不再以“触摸音量盘串口 MVP”为产品方向，而是转向 Surface Dial 风格原型：

- 编码器 = 主输入
- 屏幕 = 主反馈
- 触摸 = 辅助输入
- USB HID = 目标产品链路
- CDC 串口 = 调试/抓包/回归链路

当前状态（2026-07-03 基线）：

- 编码器旋转/按压已接线并验证可用
- GC9A01 圆屏显示正常
- CST816S 触摸可用，但将逐步从“绝对音量主交互”降级为辅助 UI
- 原生 USB 口已确认使用 `VID:PID=303A:1001`
- 主机侧 DTR/RTS 问题已修复
- 统一事件分发第一步已完成
- 当前最近自动化测试基线：`16 passed`

当前最优先目标：

- 先完成 Windows HID-only 验证
- 在“不运行 `pc-client/dial_listener.py`”的前提下，确认 Windows 是否真的能消费当前 HID 行为
- 再根据结果决定是否继续迭代 HID descriptor/report

## 接线

当前实机定位是“编码器主输入 + 屏幕主反馈 + 触摸辅助输入”。

显示线：

```text
VCC      -> 3V3
GND      -> GND
MOSI/DIN -> GPIO10
SCLK/CLK -> GPIO11
LCD_CS   -> GPIO9
LCD_DC   -> GPIO12
LCD_RST  -> GPIO13
LCD_BL   -> GPIO7
MISO     -> 不接
```

触摸线：

```text
TP_SDA -> GPIO4
TP_SCL -> GPIO5
TP_INT -> GPIO6
TP_RST -> GPIO8
```

编码器线（当前已接好并验证可用）：

```text
ENC CLK/A -> GPIO14
ENC DT/B  -> GPIO15
ENC SW    -> GPIO16
GND       -> GND
VCC       -> 3.3V
```

## 编译

```bash
arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/ESP32/esp32s3_touch_dial
```

说明：
- `USBMode=default` = USB-OTG (TinyUSB)，自定义 HID 依赖这个模式
- `CDCOnBoot=cdc` = 保留 USB CDC 串口日志，便于继续串口调试
- 如果仍用默认 `esp32:esp32:esp32s3`，arduino-cli 会落到 `USBMode=hwcdc`：
  - 现在固件仍会把调试协议挂到 native USB CDC（控制通道=`native_usb_hwcdc`）
  - 但自定义 TinyUSB HID 不会启用，`HID STATUS` 会明确提示需要切回 `USBMode=default,CDCOnBoot=cdc`

## 上传

```bash
arduino-cli upload --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' --port /dev/ttyACM0 /home/zza/projects/ESP32/esp32s3_touch_dial
```

## Ubuntu 调试

```bash
python3 tools/ubuntu_serial_debug.py --port /dev/ttyACM0
```

## Windows 验证抓取

Windows 下可直接双击：

- `tools\run_full_capture_and_analyze.bat`
  - 先抓 host-only，再抓 full capture，最后自动分析并输出报告
- `tools\run_hid_validation.bat`
  - 自动探测串口并抓取主机 + 串口信息
- `tools\run_hid_validation_host_only.bat`
  - 只抓主机 USB/HID/Ports 枚举，不碰串口

也可在 CMD 中指定参数：

```cmd
tools\run_full_capture_and_analyze.bat

tools\run_hid_validation.bat
```

推荐优先使用：

```cmd
tools\run_full_capture_and_analyze.bat
```

当前抓取脚本会：
- 先按设备身份自动识别串口，而不是依赖固定 `COMx`
- 优先选择 ESP32-S3 native USB CDC（如 `VID:PID=303A:1001`）
- 只有 native USB CDC 不存在时，才回退到 CH343/CP210/FTDI 之类桥口

它会自动：
- 生成 host-only 抓取目录
- 生成 full capture 抓取目录
- 调用 `analyze_hid_captures.py` 输出分析报告

也可单独运行：

```cmd
tools\run_hid_validation.bat
```

如需强制指定口，再传：

```cmd
tools\run_hid_validation.bat COM16 30
```

含义：
- `COM16` = 本次临时观察到的串口名，仅用于手动覆盖
- `30` = 抓取 30 秒

抓取结果默认输出到：

```text
tools\captures\<timestamp>\
```

重点文件：
- `capture.log`
- `summary.json`
- `host_pnp_usb.txt`（Windows）
- `host_cim_pnp.txt`（Windows）
- `serial_ports.json`

除现有触摸调试外，现在还支持串口模拟编码器事件：

```text
ENC LEFT
ENC RIGHT
ENC PRESS
ENC STATUS
HID STATUS
USB STATUS
```

适合做事件模型回归或在不方便操作实体编码器时做模拟验证：
- 屏幕状态区是否显示 `ENC/SIM LEFT|RIGHT|PRESS`
- 统一 rotate/press 语义是否仍保持稳定
- HID/CDC 状态输出是否正常

预期能看到：

```text
[boot] >BOOT esp32s3_touch_dial touch_mvp
[i2c] >I2C scan 0x15 found=1
[i2c] >I2C CST816S addr=0x15 chip=...
[rx] >HELLO
[tx] ACK
[mode] >MODE wired
[touch] down x=...
[volume] 37%
[press] play/pause
[mute] toggle
>HID_STATUS reason=boot usb_mode=tinyusb cdc_on_boot=1 control_channel=native_usb_tinyusb_cdc hid_supported=1 usb_started=0 hid_ready=0 product=ESP32-S3 Touch Dial
>USB started
>HID ready
>HID_STATUS reason=ready_edge usb_mode=tinyusb cdc_on_boot=1 control_channel=native_usb_tinyusb_cdc hid_supported=1 usb_started=1 hid_ready=1 product=ESP32-S3 Touch Dial
```

## 当前交互定位

当前冻结方向如下：

- 编码器左/右旋 = 主 Dial 输入
- 编码器按压 = 主确认/按压输入
- 屏幕负责显示模式、最近输入源、最近动作、HID/USB 状态
- 触摸暂时仍保留部分旧 MVP 行为，但后续会收缩为辅助 UI（模式选择、菜单确认、快捷动作等）
- 串口输出保留用于调试/抓包/回归，不再作为产品主链路

说明：

- 旧的 `>VOLUME N` / `>PRESS` / `>MUTE_TOGGLE` 仍可能作为过渡兼容输出存在
- 但产品主语义已经冻结为 relative rotate + press

## Windows HID-only 验证步骤

目标：不运行 `pc-client/dial_listener.py`，仅靠当前固件 + Windows 原生 HID 消费路径，判断当前实现是否已经可用。

最短执行顺序：

1. 烧录 TinyUSB + CDC 版本固件：

```bash
arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/ESP32/esp32s3_touch_dial
arduino-cli upload --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' --port <PORT> /home/zza/projects/ESP32/esp32s3_touch_dial
```

2. 在 Windows 上把线接到原生 USB 口，确认枚举到 `VID:PID=303A:1001`

3. 不启动 `pc-client\dial_listener.py`

4. 先执行 host-only 抓取：

```cmd
tools\run_hid_validation_host_only.bat
```

5. 再执行 full capture：

```cmd
tools\run_full_capture_and_analyze.bat
```

6. 实机操作编码器：
   - 左转
   - 右转
   - 按压

7. 记录以下结论：
   - Windows 是否看到原生 USB / HID 设备
   - 分析报告中 `usb_mode` 是否为 `tinyusb`
   - `hid_supported` 是否为 `1`
   - 是否出现 `>USB started` / `>HID ready`
   - 不依赖 listener 时，系统或目标应用是否对旋转/按压产生真实响应

结论必须落到三选一：

1. Windows 已可直接消费
2. Windows 已枚举但不能正确消费，需要调整 descriptor/report
3. 当前 HID 路线还不够，需要重新对齐更接近 Surface Dial 的兼容实现

详细记录模板见：

- `docs/plans/2026-07-03-windows-hid-only-validation-checklist.md`

## 自动化测试

```bash
python3 -m pytest tests/ -q
```
