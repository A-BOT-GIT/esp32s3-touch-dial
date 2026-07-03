# Surface Dial GitHub 技术路线决策与实施计划

> **For Hermes:** 按本文任务顺序推进；先做“后端抽象 + 维持现有 USB PoC 可验证”，再进入 BLE Dial 主线实现。

**Goal:** 基于 GitHub 成熟项目调研结果，把本项目从“USB HID 极简 PoC”推进到“可切换 Dial backend 的 Surface Dial 原型”，并明确 BLE 自定义 Dial HID 为主路线。

**Architecture:** 固件内部统一收敛到 rotate_left / rotate_right / press_pulse 事件模型；输出层拆成 Dial backend（当前 USB TinyUSB Dial PoC、后续 BLE Dial HID）。短期保持 USB 路径继续可编译、可抓包、可做 Windows HID-only 验证；中期接入 BLE Dial backend 做真正的 Surface Dial 兼容主线；串口只保留调试与回归用途。

**Tech Stack:** Arduino ESP32 core 2.0.17, ESP32-S3 native USB, TinyUSB/USBHID, 后续 BLE HID（参考 X-Knob），Python capture tools, pytest, arduino-cli。

---

## 1. 调研结论（冻结）

### 1.1 GitHub 成熟参考的共同点
- 不是把旋钮当普通音量键/Consumer Control。
- 都围绕独立的 Dial 语义：press / release / rotate。
- ESP32-S3 方向上，最强正例是 `SmallPond/X-Knob`，核心是 BLE 自定义 Dial HID，而不是 USB-only。
- AVR / Pro Micro 系项目可作为协议语义参考，但不是本项目的直接移植目标。

### 1.2 当前项目定位
- 编码器 = 主输入
- 屏幕 = 主反馈
- 触摸 = 辅助输入
- CDC 串口 = 调试/抓包/回归
- 真正的产品主语义 = relative rotate + press

### 1.3 路线决策
- 主路线：BLE 自定义 Dial HID
- 次路线：保留 USB TinyUSB Dial PoC，用于 Windows HID-only 验证和 descriptor 迭代
- 不再把“普通音量键可用”当作 Surface Dial 成功标准

---

## 2. 当前代码现状

### 2.1 已有基础
- `esp32s3_touch_dial.ino` 已有统一事件分发入口：
  - `dispatchRotateEvent(...)`
  - `dispatchPressPulseEvent(...)`
- 当前 USB TinyUSB PoC 已能发：
  - 按钮 bit
  - relative dial delta
- Windows 抓包/分析工具链已存在：
  - `tools/hid_validation_capture.py`
  - `tools/analyze_hid_captures.py`
  - `tests/test_hid_validation_capture.py`
  - `tests/test_hid_capture_analysis.py`

### 2.2 当前主要缺口
- 输出层仍是“直接写 USB HID”，没有抽象成 backend。
- 代码层还没有为 BLE Dial backend 预留统一 begin/ready/send 入口。
- 状态日志里缺少 backend 维度，后续难以对比 USB/BLE 路线。

---

## 3. 实施阶段

### Phase 1：Dial backend 抽象（本轮就做）
**Objective:** 把当前 USB Dial PoC 从“直写 HID”整理成统一 backend 入口，不改变现有行为。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Modify: `README.md`（如需补充路线说明）
- Test: `tests/test_hid_validation_capture.py`
- Test: `tests/test_hid_capture_analysis.py`

**Step 1: 抽出统一 backend 概念**
- 增加统一接口语义：
  - `beginDialBackend()`
  - `dialBackendReady()`
  - `dialBackendName()`
  - `dialBackendSendRotate(...)`
  - `dialBackendSendPressPulse()`
- 当前具体实现仍映射到 USB TinyUSB HID。
- 同时保留一个显式的 `ble_hid_planned` 命名，用于日志与后续接入点。

**Step 2: 把状态输出切到 backend 维度**
- `>HID_STATUS ...` 保持向后兼容字段不删。
- 追加：
  - `dial_backend=...`
  - `dial_backend_ready=...`
- 这样后续抓包工具不用大改就能比较 USB/BLE。

**Step 3: 把事件分发改为调用 backend 接口**
- `dispatchRotateEvent(...)` 不再直接依赖 `hidSendRotate(...)`
- `dispatchPressPulseEvent(...)` 不再直接依赖 `hidSendPressPulse()`
- 统一走 Dial backend

**Step 4: 编译与回归**
Run:
- `rtk proxy python3 -m pytest /home/zza/projects/ESP32/esp32s3_touch_dial/tests -q`
- `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/ESP32/esp32s3_touch_dial`

Expected:
- pytest 全通过
- 固件编译通过
- 当前 USB TinyUSB 路径行为不变

---

### Phase 2：BLE Dial backend 骨架
**Objective:** 在不破坏 USB 调试链路的前提下，新增 BLE Dial backend 骨架。

**Files:**
- Modify: `esp32s3_touch_dial.ino` 或拆分为 `src/ble_dial_backend.*`
- Create: `docs/plans/...`（若需单独实施文档）
- Test: 纯逻辑/状态机测试（如可抽离）

**Step 1: 参考 X-Knob 建立 BLE Dial report 结构**
- 引入独立 report id
- 保留 press/release/rotate 语义
- 先做 begin/advertise/connect/ready 状态机，不急着立刻做全量 UI

**Step 2: 增加 backend 选择策略**
优先策略建议：
1. USB TinyUSB 编译模式：默认 `usb_hid_tinyusb`
2. BLE Dial 编译模式：默认 `ble_hid_dial`
3. 若某 backend 不可用，日志中明确降级原因

**Step 3: 输出统一状态日志**
- `>HID_STATUS ... dial_backend=ble_hid_dial`
- 若 BLE 未连接：`dial_backend_ready=0`
- 若已连接可发：`dial_backend_ready=1`

---

### Phase 3：Windows 验证矩阵
**Objective:** 分清“枚举成功”和“真被 Windows 当作 Dial 消费”是两件事。

**Files:**
- Existing tools under `tools/`
- Existing docs under `docs/plans/`

**验证矩阵：**
1. USB TinyUSB 路径
   - 是否枚举
   - 是否 `hid_supported=1`
   - 是否 `dial_backend=usb_hid_tinyusb`
   - Windows 是否原生消费旋转/按压
2. BLE Dial 路径
   - 是否可配对
   - 是否能稳定重连
   - Windows 是否原生消费旋转/按压
3. 若 USB 仅枚举不消费，而 BLE 正常消费，则产品主线切到 BLE

---

## 4. 自动化测试策略

### 4.1 当前测试资产
- `tests/test_volume_ring.py`
  - UI 几何/编码器步进参考逻辑
- `tests/test_hid_validation_capture.py`
  - Windows 抓取脚本串口自动识别逻辑
- `tests/test_hid_capture_analysis.py`
  - 抓取分析报告判定逻辑

### 4.2 本轮必须维持的测试命令
```bash
rtk proxy python3 -m pytest /home/zza/projects/ESP32/esp32s3_touch_dial/tests -q
```

### 4.3 固件验证命令
```bash
rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/ESP32/esp32s3_touch_dial
```

### 4.4 覆盖矩阵
| 模块 | 验证方式 | 目标 |
|---|---|---|
| 事件分发 | 代码审查 + 编译 | 不破坏 rotate/press 主语义 |
| USB Dial backend | arduino-cli compile | 继续可编译 |
| Windows 抓取工具 | pytest | 报告逻辑不回归 |
| Windows HID-only 验证 | 手工实机 | 判断是否真被系统消费 |
| BLE Dial backend | 后续 compile + 手工配对 | 验证主路线可行性 |

---

## 5. 本轮完成标准
- 新计划文档已写入仓库
- 固件已具备统一 Dial backend 入口
- `HID_STATUS` 已带 backend 维度
- pytest 通过
- `arduino-cli compile` 通过

---

## 6. 下一轮完成标准
- BLE Dial backend 至少完成骨架与 ready 状态输出
- Windows 上完成 USB vs BLE 两条路径的主机侧对比验证
