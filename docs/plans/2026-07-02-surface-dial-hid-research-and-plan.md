# Surface Dial HID 仿真调研与实施计划

> **For Hermes:** 后续如进入实现，按本文任务拆分执行；优先 USB HID PoC，再做 BLE HID。

**Goal:** 基于当前 `esp32s3_touch_dial` 项目，研究并落地接近 Microsoft Surface Dial 的 HID 级设备仿真路线，明确 GitHub 可复用项目、EC11 旋转编码器接法/解码方式、以及 ESP32-S3 的 USB/BLE HID 可行性。

**Architecture:** 先保留当前项目的“触摸环 + 中心按压”交互语义，把输出层从串口协议逐步抽象为事件源；第一阶段新增 USB Custom HID Dial PoC，验证 Windows 对 Dial 类 HID 报告的响应；第二阶段再视 PoC 结果决定是否复制为 BLE HID 版本。避免一开始同时改交互、传输层和 PC 端代理。

**Tech Stack:** Arduino ESP32 core 2.0.17, ESP32-S3 TinyUSB/USBHID, 自定义 HID report descriptor, 可选 BLE HID（参考 X-Knob 的自定义 BLEHIDDevice 报告实现）, pytest。

---

## 1. 已验证的 GitHub 参考项目

### 1.1 `Eddddddddy/Surface_Dial_Arduino`
仓库：`https://github.com/Eddddddddy/Surface_Dial_Arduino`

本地验证依据：
- README：`/tmp/sd_research/Surface_Dial_Arduino/README.md`
- 固件：`/tmp/sd_research/Surface_Dial_Arduino/src/Surface_Dial_attiny/Surface_Dial_attiny.ino`
- HID 定义：`/tmp/sd_research/Surface_Dial_Arduino/lib/TrinketHidCombo/TrinketHidCombo.h`

确认到的关键事实：
- 明确目标就是 “surface dial function”。
- README 明确支持 EC11：
  - Pro: `EC11E1834403 (ALPS, without detent)`
  - Lite: `EC11* (With detent)`
- 不是普通音量键，而是自定义 Dial 码：
  - `DIAL_R = 0xC8`
  - `DIAL_L = 0x38`
  - `DIAL_PRESS = 0x01`
  - `DIAL_RELEASE = 0x00`
  - `DIAL_R_F = 0x14`
  - `DIAL_L_F = 0xEC`
- `Surface_Dial_attiny.ino` 使用 `TrinketHidCombo.pressMultimediaKey(...)` 发送以上 Dial 值。
- 编码器解码使用 AB 相状态机，不是简单延时轮询；支持双击切换快/慢旋转档位。

判断：
- 这是“真 Surface Dial 风格 HID 报告”的强参考，尤其适合借用 `Dial` 相关 report 值与旋转语义。
- 但硬件平台是 ATTiny85 + V-USB，不可直接搬到 ESP32-S3，只适合作为协议/交互参考。

### 1.2 `brunomlopes/pro-micro-surface-dialish`
仓库：`https://github.com/brunomlopes/pro-micro-surface-dialish`

本地验证依据：
- 固件：`/tmp/sd_research/pro-micro-surface-dialish/pro-micro-surface-dialish.ino`

确认到的关键事实：
- 注释明确写：`create a Surface Dial-compatible device`。
- 调用接口直接是：
  - `SurfaceDial.begin()`
  - `SurfaceDial.press()`
  - `SurfaceDial.release()`
  - `SurfaceDial.rotate(...)`
- 也是标准 AB 相旋转编码器解码。

判断：
- 这是“最干净的 Surface Dial 抽象接口”参考，说明在 MCU 端把交互抽象成 `press/release/rotate(delta)` 是正确方向。
- 但它依赖 Pro Micro / HID-Project 生态，不能直接用于 ESP32-S3。

### 1.3 `SmallPond/X-Knob`
仓库：`https://github.com/SmallPond/X-Knob`

本地验证依据：
- README：`/tmp/sd_research/X-Knob/README_EN.md`
- 表层实现：`/tmp/sd_research/X-Knob/1.Firmware/src/hal/surface_dial.cpp`
- BLE HID：`/tmp/sd_research/X-Knob/1.Firmware/lib/ble_kb/BleKeyboard.h`
- BLE HID 描述符与发包：`/tmp/sd_research/X-Knob/1.Firmware/lib/ble_kb/BleKeyboard.cpp`

确认到的关键事实：
- README 明确把 `Surface Dial` 列为功能之一。
- MCU 就是 `ESP32-S3 WROOM-1U-N16R8`。
- `surface_dial.cpp` 不是发普通键盘，而是：
  - `sendDialReport(DIAL_PRESS)`
  - `sendDialReport(DIAL_RELEASE)`
  - `sendDialReport(DIAL_L)`
  - `sendDialReport(DIAL_R)`
- `BleKeyboard.h` 里存在单独 Dial 常量与 `inputDialKeys`：
  - `DIAL_R = 0xC8`
  - `DIAL_L = 0x38`
  - `DIAL_PRESS = 0x01`
  - `DIAL_RELEASE = 0x00`
  - `DIAL_KEYS_ID = 10`
- `BleKeyboard.cpp` 里有单独的 Dial HID 描述符段和 `sendDialReport()`。
- `sendDialReport()` 发 2 字节报文：
  - `dial_report[0] = keys`
  - `dial_report[1] = 0 / 0xff`

判断：
- 这是“ESP32-S3 + BLE HID + 自定义 Dial 报告”最重要的正面证据。
- 它证明 ESP32-S3 不是只能做普通 BLE 键盘，而是能做接近 Surface Dial 的 BLE HID 仿真。

### 1.4 `Blendroom94/macro-keyboard`
仓库：`https://github.com/Blendroom94/macro-keyboard`

本地验证依据：
- 接线文档：`/tmp/sd_research/macro-keyboard/WIRING.md`
- 主程序：`/tmp/sd_research/macro-keyboard/src/main.cpp`

确认到的关键事实：
- 板子也是 `ESP32-S3`。
- 文档给出成熟的 EC11 接线：
  - `A / CLK -> GPIO11`
  - `B / DT -> GPIO13`
  - `SW -> GPIO12`
  - `GND -> GND`
  - `VCC -> 3.3V`
- 固件中使用：
  - 双相状态表 `ENC_TABLE`
  - detent 阈值 `ENC_DETENT = 4`
  - 反向锁定/去抖 `ENC_LOCKOUT_MS = 80`
- 当前它发的是普通 BLE 键盘/滚轮行为，不是 Surface Dial 报告。

判断：
- 这不是 Surface Dial 仿制项目，但对 `EC11 + ESP32-S3` 的稳定解码非常有参考价值。

---

## 2. 对“成熟度”的结论

### 真正可作为“Surface Dial 兼容/仿真”参考的项目
1. `Surface_Dial_Arduino`
2. `pro-micro-surface-dialish`
3. `X-Knob`

### 只能作为“旋钮硬件/输入工程实现”参考的项目
1. `macro-keyboard`

### 关键结论
- AVR / Pro Micro 生态已经证明 `press/release/rotate(delta)` 这套交互抽象和 Dial 码值是可行的。
- ESP32-S3 生态中，`X-Knob` 已证明 BLE 版自定义 Dial HID 报告可行。
- 因此当前项目缺的不是硬件能力，而是“把输出层从串口协议迁移到自定义 HID 报告”。

---

## 3. EC11 旋转编码器的建议用法

如果后续在当前项目中加入 EC11，推荐接法：

```text
EC11 signal -> ESP32-S3
A / CLK     -> 任意普通 GPIO
B / DT      -> 任意普通 GPIO
SW          -> 任意普通 GPIO
GND         -> GND
VCC         -> 3.3V
```

参考稳定实现（来自 `macro-keyboard`）：
- AB 两路用 `INPUT_PULLUP`
- A/B 都挂中断
- ISR 中维护 4-bit 状态机
- 累计到 `ENC_DETENT = 4` 视为一格
- 加 `ENC_LOCKOUT_MS ≈ 80ms` 防反向抖动
- SW 单独做按钮去抖

不推荐：
- `delay()` 轮询式解码
- 直接把每次边沿都当成一步
- 没有 detent 聚合就直接发 HID report

理由：
- Surface Dial 体验更像“离散档位变化”，不是乱跳的高速边沿流。
- 如果后面要加入菜单态 / 当前工具态，稳定步进比高频原始边沿更重要。

---

## 4. 当前 ESP32-S3 模块是否支持 HID 级设备仿真

### 4.1 USB HID：支持
本机已安装的 Arduino core：
- `esp32:esp32 2.0.17`

本机验证到的 USB HID 组件：
- `USBHID.cpp`
- `USBHID.h`
- `USBHIDKeyboard`
- `USBHIDConsumerControl`
- `USBHIDVendor`
- `CustomHIDDevice` 示例
- `CompositeDevice` 示例

本地路径示例：
- `/home/zza/.arduino15/packages/esp32/hardware/esp32/2.0.17/libraries/USB/src/USBHID.h`
- `/home/zza/.arduino15/packages/esp32/hardware/esp32/2.0.17/libraries/USB/src/USBHIDVendor.h`
- `/home/zza/.arduino15/packages/esp32/hardware/esp32/2.0.17/libraries/USB/examples/CustomHIDDevice/CustomHIDDevice.ino`
- `/home/zza/.arduino15/packages/esp32/hardware/esp32/2.0.17/libraries/USB/examples/CompositeDevice/CompositeDevice.ino`

明确证据：
- `USBHID::addDevice(USBHIDDevice * device, uint16_t descriptor_len)` 存在
- `USBHIDDevice::_onGetDescriptor(uint8_t* buffer)` 可自定义 HID report descriptor
- 说明 ESP32-S3 USB 栈支持自定义 HID 描述符，不限于键盘/鼠标/消费者控制

判断：
- USB 自定义 HID Dial PoC 可行。
- 这是当前项目最优先尝试的路线。

### 4.2 BLE HID：支持
直接证据：
- `X-Knob` 已在 ESP32-S3 上实现自定义 Dial BLE HID 报告。

判断：
- BLE 路线可行，但调试成本高于 USB。
- 不适合在当前项目里作为第一步落地。

---

## 5. 对当前项目的路线建议

### 推荐顺序：USB HID PoC -> BLE HID -> 再考虑保留/移除 PC 端代理

原因：
1. 当前项目本来就是有线 USB 连接电脑。
2. USB HID 比 BLE 更容易调试。
3. 可以在保留串口日志的前提下逐步增加 HID 设备功能。
4. 一旦 USB HID PoC 成功，再复制同样的事件模型到 BLE 版，风险更低。

### 不推荐的顺序
- 先做 BLE HID，再研究 USB
- 一开始就把串口 listener 全删掉
- 一开始就同时支持触摸环、EC11、BLE、USB 四套输入/输出路径

原因：
- 变量太多，不利于定位是 descriptor 问题、Windows 识别问题，还是交互问题。

---

## 6. 当前仓库里的建议架构

### 6.1 保留现有交互层
当前固件：
- `esp32s3_touch_dial.ino`

已经具备：
- 触摸环 -> 音量值/旋转语义
- 中心短按 / 长按语义
- 屏幕 UI
- 串口调试能力

建议不要立刻推翻它，而是先把“输出层”抽象出来：

```text
Touch / Center Press
        ↓
DialEvent 抽象层
  - rotate_left(step)
  - rotate_right(step)
  - button_press()
  - button_release()
        ↓
Backend
  - SerialBackend   (现有协议)
  - UsbHidBackend   (新增 PoC)
  - BleHidBackend   (后续)
```

### 6.2 输入源可后续扩展 EC11
后续如要加 EC11，不应直接写死到现有 UI 代码里，而应作为第二输入源：

```text
Input sources
- touch ring
- center touch
- ec11 rotation
- ec11 switch

都统一映射为 DialEvent
```

这样可以：
- 不破坏现有触摸版验证成果
- EC11 可作为“真实物理手感版”增量加入
- 同一套 HID backend 可复用

---

## 7. 最小可行 PoC 设计

### PoC 目标
在当前项目中新增一个最小 USB HID 自定义 Dial 模式，验证：
- ESP32-S3 能正常枚举为自定义 HID 设备
- Windows 能收到类似 Dial 的输入报文
- 当前触摸环/中心按压能映射成 HID 报告发送

### PoC 不做的事
- 不先接入 BLE
- 不先引入 EC11
- 不先删除原串口协议
- 不先重构所有 UI
- 不先做 Surface Studio on-screen 行为

### PoC 需要验证的最小事件
1. `button_press`
2. `button_release`
3. `rotate_left`
4. `rotate_right`

### PoC 优先复用的值
优先参考下面项目中的 Dial 值：
- `Surface_Dial_Arduino`
- `X-Knob`

当前已验证一致的关键值：
- `DIAL_PRESS = 0x01`
- `DIAL_RELEASE = 0x00`
- `DIAL_R = 0xC8`
- `DIAL_L = 0x38`

---

## 8. 实施任务拆分

### Task 1: 在当前仓库内保存 HID 调研文档
**Objective:** 把调研结论固化到仓库，作为后续实现依据。

**Files:**
- Create: `docs/plans/2026-07-02-surface-dial-hid-research-and-plan.md`
- Modify: `WORK_SUMMARY.md`

**Verification:**
- 文档已在仓库内可读
- `WORK_SUMMARY.md` 能指向该文档

### Task 2: 提取当前固件的 DialEvent 抽象
**Objective:** 把现有触摸事件与输出层解耦。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Test: `tests/test_volume_ring.py`（必要时新增事件映射测试）

**Steps:**
1. 定义 `DialEventType` / `DialBackend` 风格接口或等价函数组。
2. 保留现有串口输出作为 `SerialBackend`。
3. 让触摸环不再直接 `Serial.printf(">VOLUME ...")`，而是先映射成事件。
4. 保持现有协议行为不变。

**Run:**
- `rtk proxy python3 -m pytest /home/zza/projects/ESP32/esp32s3_touch_dial/tests -q`

### Task 3: 新增最小 USB HID backend
**Objective:** 让 ESP32-S3 能发出自定义 HID Dial 报告。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Create（如需要拆分）:
  - `src/usb_dial_hid.h`
  - `src/usb_dial_hid.cpp`
- Reference:
  - ESP32 core `USBHID.h`
  - `CustomHIDDevice` 示例

**Step 1: 写 failing 编译/接口测试（如果能独立测试则写）**
- 至少保证代码组织可单独编译。

**Step 2: 实现最小 descriptor**
- 先定义 Dial report descriptor
- 再实现 `send_press/send_release/send_left/send_right`

**Step 3: 本地编译验证**
Run:
- `rtk proxy arduino-cli compile --fqbn esp32:esp32:esp32s3 /home/zza/projects/ESP32/esp32s3_touch_dial`

Expected:
- 编译成功

### Task 4: 增加 HID/Serial 双模式开关
**Objective:** 不破坏现有串口 listener 路线，允许独立切换验证。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Modify: `README.md`

**Implementation direction:**
- 编译期开关或运行时模式开关均可
- 第一版优先编译期开关，降低复杂度

### Task 5: Windows 端 PoC 验证记录
**Objective:** 记录 Windows 对自定义 HID PoC 的枚举与实际行为。

**Files:**
- Modify: `WORK_SUMMARY.md`
- Optional: `docs/plans/windows-hid-validation-notes.md`

**Verification checklist:**
- 设备是否能成功枚举
- 是否出现 HID 输入设备
- 旋转左右是否收到事件
- 按压是否收到事件
- 是否被系统当作普通键盘/消费者控制，还是更接近 Dial 类输入

### Task 6: 决定是否进入 BLE HID 阶段
**Objective:** 只有 USB PoC 结论清晰后，才进入 BLE。

**Decision rule:**
- 如果 USB PoC 能工作，就复制相同事件模型到 BLE
- 如果 USB PoC 不能工作，先查 descriptor / Windows 识别层问题，不要立刻切 BLE

---

## 9. 自动化测试策略

### 当前可自动化的部分
1. 几何映射 / 触摸逻辑
   - `tests/test_volume_ring.py`
2. 事件映射（后续新增）
   - 例如：触摸环方向 -> `rotate_left/right`
   - 中心短按/长按 -> `press/release` or mode event
3. 输出层单元测试（若抽象为纯 C++ 函数难做，可先做 Python 旁证或最小编译检查）

### 当前不可完全自动化的部分
1. Windows 是否按 Surface Dial 语义接受该 descriptor
2. 真实 USB/BLE 枚举行为
3. 系统级菜单/原生 Dial 响应

### 推荐测试矩阵
| 模块 | 目标 | 自动化方式 |
|---|---|---|
| 触摸几何 | 输入映射正确 | pytest |
| DialEvent 抽象 | 触摸/按压 -> 事件正确 | pytest / 纯函数测试 |
| USB HID backend | 编译通过 | `arduino-cli compile` |
| Windows HID 行为 | 枚举与输入有效 | 手工验证 |
| BLE HID 行为 | 配对/重连/输入有效 | 手工验证 |

### 推荐执行命令
```bash
rtk proxy python3 -m pytest /home/zza/projects/ESP32/esp32s3_touch_dial/tests -q
rtk proxy arduino-cli compile --fqbn esp32:esp32:esp32s3 /home/zza/projects/ESP32/esp32s3_touch_dial
```

---

## 10. 最终建议

### 推荐路线（按优先级）
1. 先做 `USB Custom HID Dial PoC`
2. 保留现有串口 listener 路线，不要立刻删
3. 把触摸环/中心按压抽象成统一 `DialEvent`
4. 等 USB 跑通后，再复制成 BLE HID 版本
5. EC11 作为第二输入源后加，不要挡住当前触摸版本推进

### 这条路线的原因
- 当前项目已有触摸交互和屏幕 UI，不该因为研究 HID 而推翻。
- ESP32-S3 + Arduino core 已确认具备 USB 自定义 HID 能力。
- `X-Knob` 已确认具备 BLE 自定义 Dial HID 能力。
- 因而最现实的策略是：
  - 先验证 USB descriptor / Windows 行为
  - 再决定是否值得上 BLE

### 一句话判断
当前项目完全有条件进入“HID 级 Surface Dial 仿真”的 PoC 阶段；下一步不是继续搜资料，而是开始做 `USB HID Dial` 最小实现。
