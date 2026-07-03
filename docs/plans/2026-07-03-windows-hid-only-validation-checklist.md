# Windows HID-only 验证清单

> 目标：在不运行 `pc-client/dial_listener.py` 的前提下，验证当前 ESP32-S3 Touch Dial 固件是否已经能被 Windows 作为可消费的 HID 设备使用，并把结论收敛到明确的后续动作。

---

## 0. 本轮验证的通过定义

本轮不追求“看起来枚举到了 HID”，而是追求一个明确结论：

1. Windows 已可直接消费
2. Windows 已枚举但不能正确消费，需要调整 descriptor/report
3. 当前 HID 路线还不够，需要重新对齐更接近 Surface Dial 的兼容实现

如果最终不能落到这三类之一，本轮验证视为未完成。

---

## 1. 验证前准备

### 固件前提

应使用 TinyUSB + CDC 版本构建，而不是 hwcdc-only 构建：

```bash
arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/ESP32/esp32s3_touch_dial
arduino-cli upload --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' --port <PORT> /home/zza/projects/ESP32/esp32s3_touch_dial
```

原因：

- `USBMode=default` = TinyUSB 路径，可启用自定义 HID
- `CDCOnBoot=cdc` = 保留 CDC 调试口，便于抓状态
- 若跑在 `hwcdc`，分析脚本通常会给出：`hid_supported=0`

### 接线前提

- 使用 ESP32-S3 原生 USB 口
- 目标枚举身份优先看：`VID:PID=303A:1001`
- 不要把 CH343/桥口当成 HID-only 验证主口

### Windows 前提

- 本轮不要启动 `pc-client\dial_listener.py`
- 若此前配置过其自启动，先确认它未在后台运行
- 关闭与本设备验证无关的串口终端、抓串口工具、桥口监控工具

---

## 2. 最短执行顺序

### Step 1: 连接设备

将线接到原生 USB 口，然后等待 Windows 枚举完成。

记录：

- 是否出现 `USB JTAG/Serial debug unit`
- 是否出现 `ESP32-S3 Touch Dial`
- 是否出现 HIDClass 条目

### Step 2: host-only 抓取

运行：

```cmd
tools\run_hid_validation_host_only.bat
```

目标：

- 先固定一份“只看主机枚举”的证据
- 不让串口交互影响第一轮判断

产物目录：

```text
tools\captures\<timestamp>\
```

至少检查：

- `host_pnp_usb.txt`
- `host_cim_pnp.txt`

### Step 3: full capture

运行：

```cmd
tools\run_full_capture_and_analyze.bat
```

如自动选口不稳定，手动指定本轮临时 COM 号：

```cmd
tools\run_full_capture_and_analyze.bat COM16 30
```

目标：

- 捕获 Windows 枚举
- 捕获 CDC 状态输出
- 自动产出 `analysis_report.txt`
- 自动判断是否误选桥口/是否仍处于 hwcdc/是否已进入 tinyusb HID 路径

### Step 4: 实机操作

在 full capture 期间，对设备做真实操作：

- 编码器左转
- 编码器右转
- 编码器按压

并同时观察：

- Windows 系统是否有直接反应
- 某个目标应用是否有直接反应
- 屏幕是否显示最近动作
- 抓取日志里是否出现 HID/USB ready 相关状态

---

## 3. 必查字段

在 `analysis_report.txt` 或 `capture.log` 中，重点看以下字段。

### 枚举与口选择

- `preferred_port`
- `preferred_port_kind`
- `selected_port_matches_preferred`
- 是否出现“本次抓取选错串口”

正确倾向：

- `preferred_port_kind: native_usb`
- `selected_port_matches_preferred: True`

### 固件 HID 状态

- `usb_mode`
- `control_channel`
- `hid_supported`
- `usb_started_count`
- `hid_ready_count`

正确倾向：

- `usb_mode: tinyusb`
- `control_channel: native_usb_tinyusb_cdc`
- `hid_supported: True`
- 出现 `>USB started`
- 出现 `>HID ready`

### 错误信号

若看到以下情况，应直接判为“还不能进入 HID-only 可用结论”：

1. `usb_mode: hwcdc` 且 `hid_supported: False`
   - 说明当前只是 native USB CDC 可用，自定义 HID 没开

2. 只看到桥口，没有看到 `VID_303A` / `ESP32-S3` / `Touch Dial`
   - 说明 native USB 路径还没真正进入验证状态

3. 明明看到了 native USB，但 `selected_port` 抓的是桥口
   - 说明抓取证据已被错误串口污染，需要重跑

4. `hid_supported: True`，但始终没有 `>USB started` / `>HID ready`
   - 说明 TinyUSB HID 路径没真正 ready，需要继续查枚举或初始化

---

## 4. 结果判定规则

### 结论 A：Windows 已可直接消费

满足倾向：

- Windows 已明确枚举原生 USB / HID
- 固件处于 `tinyusb` 且 `hid_supported=1`
- 有 `>USB started` / `>HID ready`
- 不运行 listener 时，系统或目标应用对旋转/按压有真实响应

下一步：

- 开始做触摸辅助化
- 清理过渡日志
- 完善 README/交付路径

### 结论 B：Windows 已枚举但不能正确消费，需要调整 descriptor/report

满足倾向：

- Windows 已看到 HID / 原生 USB
- 固件状态显示 HID 路径已启用
- 但真实旋转/按压没有被系统或目标应用正确消费

下一步：

- 聚焦 descriptor/report 迭代
- 重点检查 top-level usage / collection / relative delta / press pulse 发包节奏
- 每改一次 descriptor，都必须重新抓证据

### 结论 C：当前 HID 路线还不够，需要重新对齐更接近 Surface Dial 的兼容实现

满足倾向：

- 即使进入 tinyusb + hid_supported=1，也仍无法让 Windows 在目标场景中正确消费
- 说明不只是“小修 descriptor”能解决，而可能需要更接近已验证实现的 usage/collection/report 组织

下一步：

- 回看参考实现
- 对齐更接近 Surface Dial 的 descriptor 结构
- 重新组织 press/rotate 事件报文模型

---

## 5. 本轮记录模板

请把本轮实际结果填到下面：

```text
验证日期：
固件构建：
使用 USB 口：
Windows 机器：

A. 枚举结果
- 是否看到 VID:PID=303A:1001：
- 是否看到 HIDClass 条目：
- 是否同时看到桥口 CH343：

B. 抓取结果
- host-only 目录：
- full-capture 目录：
- analysis_report.txt 路径：

C. 关键字段
- preferred_port:
- preferred_port_kind:
- selected_port_matches_preferred:
- usb_mode:
- control_channel:
- hid_supported:
- usb_started_count:
- hid_ready_count:

D. 实机行为
- 左转效果：
- 右转效果：
- 按压效果：
- 无 listener 时系统/应用是否真实响应：

E. 最终结论（三选一）
- [ ] Windows 已可直接消费
- [ ] Windows 已枚举但不能正确消费，需要调整 descriptor/report
- [ ] 当前 HID 路线还不够，需要重新对齐更接近 Surface Dial 的兼容实现

F. 下一步动作
-
```

---

## 6. 本轮最重要的纪律

- 先证据，后结论
- 不接受“看起来像是有 HID 了”
- 不接受“Windows 好像没反应，先去改 UI”
- 如果 HID-only 结论没收敛，后续工作优先级不应转到触摸美化
