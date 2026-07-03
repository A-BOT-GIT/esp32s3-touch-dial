# Encoder + Screen Surface Dial 执行计划

> **For Hermes:** 后续实现按本文任务顺序推进；优先完成 HID-only Windows 验证，再决定是否继续扩展触摸辅助能力。

**Goal:** 基于当前已接通并验证可用的 ESP32-S3 + 编码器 + 圆屏硬件，把项目从“串口 MVP + 调试型 HID”推进到“编码器主输入、屏幕状态增强、尽量接近 Surface Dial 的原生 HID 设备”。

**Architecture:** 以编码器作为主 Dial 输入源（rotate + press），圆屏作为状态显示与辅助交互层；保留 CDC 串口仅用于调试、抓包和回归，不再作为产品主链路。短期目标是完成 USB HID-only Windows 验证；中期目标是把触摸从“绝对音量环”收缩为辅助模式/菜单输入；长期目标是形成无需 Win 常驻服务的 Surface Dial 风格设备。

**Tech Stack:** Arduino ESP32 core 2.0.17, TinyUSB/USBHID, ESP32-S3 native USB CDC, EC11-style encoder input, GC9A01 display, CST816S touch, Python capture tools, pytest.

---

## 0. 当前基线（已确认）

### 已完成能力
- 编码器旋转事件已实测正常：`>ENC source=ENC dir=LEFT/RIGHT`
- 编码器按压已实测正常：`>ENC_PRESS source=ENC` / `>PRESS`
- 设备可进入 `>MODE wired`
- HID 状态查询正常：`>ENC_STATUS ... hid=ready`
- 主机侧 DTR/RTS bug 已修复：
  - `pc-client/dial_listener.py`
  - `tools/hid_validation_capture.py`
- 当前原生 USB 口已确认：`VID:PID=303A:1001`

### 当前主要问题
- 当前交互主路径仍偏向串口 MVP
- 触摸环仍是“绝对音量盘”语义，不像 Dial
- HID 已存在，但尚未证明 Windows 能在无 listener 时把它当作真正可消费的 Dial 设备
- 固件中仍有临时探针日志 `>PROBE ...`

---

## 1. 产品方向决策（冻结）

### 决策 1：主输入模型
**结论：采用 A 方案，做成“A 为主、B 为辅”。**

- 编码器：主输入
- 屏幕：状态显示 + 辅助 UI
- 触摸：辅助输入，不与编码器完全对等

### 为什么冻结这个决策
- 更接近 Surface Dial 的核心语义：relative rotate + press
- 降低双输入完全对等带来的复杂度
- 先把 HID 主链路做稳，再扩展触摸增强能力

### 现在不做的事
- 不把触摸环继续作为主产品交互
- 不把屏幕/触摸与编码器做成两个完全平行的 Dial 主入口
- 不继续把 PC listener 作为最终用户链路

---

## 2. 阶段目标

### Phase 1：把编码器变成稳定主输入
**目标结果：** 在 Linux/Windows 调试时，编码器左转、右转、按压都能稳定触发统一事件模型；屏幕正确显示状态。

### Phase 2：完成 Windows HID-only 验证
**目标结果：** 不运行 `pc-client/dial_listener.py`，只靠 USB HID，验证 Windows 端是否能识别并消费旋转/按压行为。

### Phase 3：收缩串口 MVP 到 debug only
**目标结果：** 串口仅保留日志、诊断、抓包、回归，不再承载产品主功能输出。

### Phase 4：把触摸改造成辅助 UI
**目标结果：** 触摸不再直出绝对音量，而是用于模式选择、菜单确认、快捷动作或参数页。

### Phase 5：形成可交付原型
**目标结果：** 去掉探针日志，文档更新，形成一条明确的“烧录 -> 插上 Windows -> 验证 HID -> 使用”的路径。

---

## 3. 任务拆解

### Task 1：整理并冻结事件模型

**Objective:** 明确固件内部统一事件抽象，避免继续围绕 `>VOLUME N` 演进。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Test: `tests/` 下新增事件模型相关测试（如适用）

**需要冻结的事件语义：**
- `rotate_left(step=1)`
- `rotate_right(step=1)`
- `press_down()`
- `press_up()` 或 `press_pulse()`
- `long_press()`（仅当真需要）
- `mode_change(...)`

**验收标准：**
- 编码器路径和未来触摸辅助路径都能映射到同一套事件模型
- 业务逻辑不再直接依赖 `>VOLUME N` 作为主语义

---

### Task 2：让编码器路径成为第一优先级

**Objective:** 固件逻辑上明确“编码器是主 Dial 输入源”。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Test: 新增/更新编码器行为测试（若可抽离纯逻辑）

**具体工作：**
1. 保留当前 `emitEncoderStep()` / `emitEncoderPress()` 路径
2. 审查是否存在触摸逻辑覆盖或抢占编码器状态显示的情况
3. 屏幕主状态文案从“触摸音量盘”调整为更偏 Dial 状态
4. 需要时增加屏幕显示：
   - 当前模式
   - 最近输入源（ENC / TOUCH / USB）
   - 最近动作（LEFT / RIGHT / PRESS）

**验收标准：**
- 编码器成为最稳定、最可预测的主输入
- 屏幕反馈优先围绕编码器动作设计

---

### Task 3：完成 Windows HID-only 验证

**Objective:** 验证当前 HID descriptor/report 是否足以在无 Win listener 的情况下被 Windows 真实消费。

**Files:**
- Use: `esp32s3_touch_dial.ino`
- Use: `tools/hid_validation_capture.py`
- Use: `tools/run_full_capture_and_analyze.bat`
- Create/Modify: `docs/plans/...` 或 `README.md` 中补充验证记录

**执行步骤：**
1. 烧录当前 HID 版本固件
2. 在 Windows 上连接原生 USB 口（303A:1001）
3. 不启动 `pc-client/dial_listener.py`
4. 先做系统枚举抓取
5. 再做真实旋转/按压测试
6. 记录：
   - Windows 是否出现 HID 设备
   - 应用/系统是否对旋转与按压有反应
   - 是否需要继续调整 descriptor

**验收标准：**
- 必须得到明确结论，不能停留在“看起来有 HID”
- 结论只有三种：
  1. Windows 已可直接消费
  2. Windows 已枚举但不能正确消费，需要调整 descriptor
  3. 当前 HID 路线不够，需要重新对齐 Surface Dial 兼容实现

---

### Task 4：根据 HID-only 结果决定 descriptor 迭代方向

**Objective:** 如果 HID-only 不通，集中修改 descriptor/report，而不是继续堆叠 PC 代理逻辑。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Test/Artifact: Windows 抓取产物 `tools/captures/...`

**重点检查：**
- Top-level Usage / Collection 是否正确
- Button + Dial relative delta 的 report 组织是否符合 Windows 预期
- `press/release/rotate(delta)` 的发包节奏是否合理
- 是否需要更贴近已验证参考项目中的 Dial 码值/报文模式

**验收标准：**
- 每次 descriptor 修改都配套一轮 Windows 枚举与行为验证
- 不接受“只改代码不抓证据”

---

### Task 5：把触摸从主功能改成辅助 UI

**Objective:** 避免产品停留在“圆形触摸音量盘”，把触摸退到辅助层。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Test: `tests/test_volume_ring.py` 可能拆分/重命名为更通用的触摸 UI 测试

**建议触摸职责：**
- 模式切换
- 菜单选择
- 参数确认
- 快捷动作
- 可选：页面滑动/退出

**不建议继续保留为主语义：**
- 外圈触摸直接映射绝对系统音量

**验收标准：**
- 主产品叙事从“触摸音量盘”转成“带屏 Dial 控制器”

---

### Task 6：清理调试痕迹并恢复正式固件输出

**Objective:** 移除临时探针日志，保留必要状态诊断。

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Modify: `README.md`

**需要处理：**
- 去掉 `>PROBE ...`
- 保留：
  - `>BOOT`
  - `>MODE`
  - `>HID_STATUS`
  - 必要的调试命令
- 明确区分：debug build / normal build（若需要）

**验收标准：**
- 正式固件输出干净
- 调试命令仍够用

---

### Task 7：更新交付文档

**Objective:** 让后续使用与验证路径清晰，不再依赖口头背景。

**Files:**
- Modify: `README.md`
- Optional: 新增 `docs/plans/verification-checklist.md`

**文档必须写清楚：**
- 两个 USB-C 口分别是什么（原生 USB vs 桥口，如适用）
- 现在应优先使用哪个口
- 编码器接线
- 当前交互定位：编码器主输入、屏幕主反馈、触摸辅助
- Windows HID-only 验证步骤
- 如果仍需要 PC listener，它仅是兼容/调试工具，不是最终依赖

---

## 4. 测试策略（必须执行）

### Test Inventory
- 固件纯逻辑测试：`tests/*.py`
- PC 协议/工具测试：
  - `pc-client/tests/test_volume_protocol.py`
  - `tests/test_hid_validation_capture_analysis.py`
- 串口真实验证：`tools/hid_validation_capture.py`
- Windows 真实枚举/行为验证：`tools/run_full_capture_and_analyze.bat`

### 覆盖矩阵
1. 输入层
- 编码器左/右/按压
- 触摸辅助动作（后续）

2. 设备层
- HID status / ready
- CDC 调试链路
- descriptor 修改后的 Windows 枚举变化

3. 产品层
- 无 listener 时是否工作
- 有 listener 时是否仍兼容调试/回归

### 推荐测试顺序
1. `python3 -m pytest tests/ -q`
2. Linux 真机串口验证（DTR=True, RTS=False）
3. Windows host-only 抓取
4. Windows full capture
5. Windows HID-only 实机操作验证

---

## 5. 里程碑定义

### M1：编码器主输入稳定
达成条件：
- 左/右旋与按压稳定
- 屏幕反馈正确
- 串口状态与日志正常

### M2：Windows HID-only 有明确结论
达成条件：
- 已完成一轮不依赖 listener 的验证
- 已得到“可用 / 不可用 / 需调 descriptor”结论

### M3：串口降级为 debug only
达成条件：
- 产品主行为不再依赖 `>VOLUME N` / `>PRESS` 这类串口协议
- 串口仅保留调试和回归价值

### M4：形成带屏 Dial 原型
达成条件：
- 编码器为主
- 屏幕为主反馈
- 触摸辅助化
- README 可指导他人复现

---

## 6. 最近两周的最短路径

### Week 1
1. 冻结“编码器主、屏幕辅、触摸辅助”方向
2. 清理代码中仍以触摸绝对音量为主的叙事/状态文案
3. 完成 Windows HID-only 验证
4. 记录结论并决定是否需要 descriptor 迭代

### Week 2
1. 若 HID-only 不通：集中调 descriptor + 反复抓证据
2. 若 HID-only 已通：开始把触摸改为辅助 UI
3. 去掉临时探针日志
4. 更新 README 与验证清单

---

## 7. 现在立刻该做什么

按优先级排序：
1. 先做 Windows HID-only 验证
2. 再根据验证结果决定 descriptor 是否要继续打磨
3. 最后再做触摸辅助化与文档收尾

**原因：** 当前最大不确定项不是编码器，也不是屏幕，而是“Windows 是否已经真的接受这套 HID 设备模型”。先消灭这个不确定项，后面的工作才不会跑偏。
