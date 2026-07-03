# esp8266-dial 功能移植与联调工作总结

日期：2026-07-02

## 1. 目标

将 GitHub 项目 `A-BOT-GIT/esp8266-dial` 的核心交互能力移植到本地触摸屏硬件方案上：

- 硬件端：ESP32-S3 + GC9A01 圆屏 + CST816S 触摸
- 交互替代：用触摸环与中心触摸替代原实体旋钮/按键
- PC 端：兼容并扩展 `esp8266-dial` 的 Windows listener
- 功能目标：
  - 触摸环控制系统音量
  - 中心短按 = 播放/暂停
  - 中心长按 = 静音切换
  - USB 串口自动识别并通信
  - Windows 端只绑定 `Realtek(R) Audio`

---

## 2. 主要涉及目录与文件

### 固件侧
- `/home/zza/projects/ESP32/esp32s3_touch_dial/esp32s3_touch_dial.ino`
- `/home/zza/projects/ESP32/esp32s3_touch_dial/tests/test_volume_ring.py`
- `/home/zza/projects/ESP32/esp32s3_touch_dial/tools/ubuntu_serial_debug.py`

### PC 端
- `/home/zza/projects/ESP32/esp32s3_touch_dial/pc-client/dial_listener.py`
- `/home/zza/projects/ESP32/esp32s3_touch_dial/pc-client/tests/test_volume_protocol.py`

---

## 3. 已完成的核心工作

### 3.1 触摸音量环移植

已在 ESP32-S3 设备上实现：

- 触摸环映射到 0~100 音量百分比
- 通过串口发送 `>VOLUME N`
- 中心短按发送 `>PRESS`
- 中心长按发送 `>MUTE_TOGGLE`
- 与 PC 端通过 `>HELLO / ACK / >PING / ACK` 进行握手与保活

当前协议侧已可对接修改后的 Windows listener。

---

### 3.2 UI 绘制与显示修复

已完成以下显示相关修复：

1. 去掉频繁整屏重绘造成的卡顿与闪烁
2. 改为以局部更新为主，减少屏幕刷新负担
3. 修复中心文字被黑色圆盘遮挡的问题
4. 将音量条颜色临时统一为黄色，避免此前蓝/绿弧段错位视觉问题
5. 修正音量减少时的“消失动画方向错误”问题

当前逻辑：
- 音量增大：只补画新增弧段
- 音量减小：从旧音量条末端向新位置回退擦除
- 开机、模式切换、PRESS、MUTE 等状态仍允许整屏重画

---

### 3.3 固件状态机修复（`>MODE boot` / `>MODE wired`）

已确认旧逻辑问题：

- 启动后会发 `>BOOT ...`
- 进入 wired 后，如果超时掉线，会再次进入 `enterBoot()` 并发送 `>MODE boot`
- 这会导致实际日志中反复出现：
  - `>MODE boot`
  - `>MODE wired`

已完成修复：

1. `>MODE boot` 仅在真正启动时发送一次
   - 增加 `bootModeSent`
   - 在 `setup()` 中发送一次后不再重复发

2. 握手成功进入工作态后，不再因为普通掉线回到 `boot`
   - 原掉线逻辑：`enterBoot()`
   - 现改为：`enterWaitPc()`
   - 行为变更：掉线后只回 `WAIT PC` UI，不再发 `>MODE boot`

3. 进入 `wired` 时同步刷新 `lastAckMs`
   - 避免因旧时间戳造成刚连上又立即判定超时

当前预期行为：
- 真启动：发一次 `>MODE boot`
- 收到 ACK：进入 `>MODE wired`
- 后续若真实断连：只回 `WAIT PC`，不再发新的 `>MODE boot`

---

### 3.4 中心按键防抖

为避免中心短按连续两次触发，已增加防抖：

- 新增 `PRESS_DEBOUNCE_MS = 300`
- 新增 `lastPressMs`
- 仅当满足以下条件才发送 `>PRESS`：
  - 位于中心区域
  - 未触发长按
  - 按下时长小于 `TAP_MAX_MS`
  - 距离上一次 `PRESS` 已超过防抖时间

效果：
- 抬手抖动不再容易导致两次 `>PRESS`

---

### 3.5 Windows listener 串口兼容性增强

已修复/增强 Windows 端对 ESP32-S3 / CH343 / 泛化串口描述的识别能力：

- 支持根据 `description / manufacturer / hwid / device` 多字段识别
- 支持 VID 白名单兜底：
  - `0x303A`
  - `0x10C4`
  - `0x1A86`
- 增加环境变量手动指定串口：
  - Windows: `set DIAL_SERIAL_PORT=COM14`
  - Linux: `DIAL_SERIAL_PORT=/dev/ttyACM0 python ...`

并已兼容裸格式：
- `>PRESS`
- `>PRESS #1`

---

### 3.6 Windows 音频控制修复

#### 3.6.1 COM 初始化问题修复

曾出现错误：

- `[WinError -2147221008] 尚未调用 CoInitialize。`

原因：
- 串口读取线程里调用 pycaw/comtypes 时没有先进行线程级 COM 初始化

已修复：
- 在 `AudioController` 中加入 `_ensure_com_initialized()`
- 在 `GetSpeakers()` 之前调用 `CoInitialize()`

结果：
- Windows 端已能正确设置系统音量并执行播放/暂停

#### 3.6.2 只绑定 `Realtek(R) Audio`

已实现：
- `TARGET_AUDIO_NAME = "Realtek(R) Audio"`
- 优先从 `AudioUtilities.GetAllDevices()` 枚举设备中查找 `FriendlyName` 包含该名称的设备
- 找不到时拒绝绑定其他设备，不再退回到默认设备

当前行为：
- 不是“优先 Realtek”
- 而是“只绑定 Realtek(R) Audio”

---

## 4. 测试与验证结果

### 4.1 固件几何与触摸映射测试
文件：`/home/zza/projects/ESP32/esp32s3_touch_dial/tests/test_volume_ring.py`

结果：
- `9 passed`

覆盖内容包括：
- 左下 = 0%
- 顶部 ≈ 50%
- 右下 = 100%
- 中心区忽略
- 底部缺口忽略
- 圆弧增减更新区间判断

---

### 4.2 PC 协议与音频控制测试
文件：`/home/zza/projects/ESP32/esp32s3_touch_dial/pc-client/tests/test_volume_protocol.py`

结果：
- `12 passed`

覆盖内容包括：
- 串口识别兼容
- 裸 `>PRESS` 协议兼容
- `DIAL_SERIAL_PORT` 手动串口指定
- COM 初始化顺序正确
- `Realtek(R) Audio` 定向绑定逻辑
- 绝对音量值写入范围钳制

---

### 4.3 固件编译与烧录

最近一次编译结果：
- `Sketch uses 309245 bytes (23%) of program storage space`

最近一次烧录结果：
- `Hash of data verified`
- `Hard resetting via RTS pin`
- 设备端口：`/dev/ttyACM0`

说明：
- 当前固件已成功编译并烧录到本地 ESP32-S3 设备

---

## 5. Surface Dial / HID 仿真调研补充

已新增调研与实施计划文档：
- `/home/zza/projects/ESP32/esp32s3_touch_dial/docs/plans/2026-07-02-surface-dial-hid-research-and-plan.md`

其中已沉淀：
- GitHub 上成熟的 Surface Dial 仿制/兼容项目筛选结果
- EC11 在 ESP32-S3 上的推荐接法与稳定解码策略
- 当前模块走 USB HID / BLE HID 的可行性判断
- 下一步建议优先做 `USB Custom HID Dial PoC`

## 6. 当前预期运行行为

### 固件侧
- 上电后只发送一次 `>MODE boot`
- 未握手时周期性发送 `>HELLO`
- 收到 `ACK` 后进入 `wired`
- 工作中周期性发送 `>PING`
- 若超时断连，只回 `WAIT PC`，不再重新发 `>MODE boot`

### 触摸交互
- 外圈拖动：发送 `>VOLUME N`
- 中心短按：发送 `>PRESS`
- 中心长按：发送 `>MUTE_TOGGLE`
- 中心短按已有额外防抖

### Windows 端
- 串口可自动识别 ESP32 / CH343 / ACM / CP210 / FTDI 等常见信息
- 仅绑定 `Realtek(R) Audio`
- 音量按绝对值设置
- `>PRESS` 用于播放/暂停

---

## 6. 建议下一步实机复核项

建议在 Windows 端用最新 listener 再观察一轮日志，重点确认：

1. 开机后只出现一次：
   - `>MODE boot`

2. 握手成功后进入：
   - `>MODE wired`

3. 正常使用时不再频繁出现：
   - `>MODE boot`
   - `>MODE wired`

4. 中心短按不再连续触发两次播放/暂停

5. 日志中绑定设备名称确实为：
   - `Realtek(R) Audio`

---

## 7. 当前产出结论

本次工作已经把 `esp8266-dial` 的核心旋钮功能，迁移为可在本地 ESP32-S3 触摸圆屏硬件上运行的版本，并完成了与修改版 Windows listener 的协议、串口识别、音频控制与 UI 交互联调。

当前已具备：
- 触摸音量控制
- 中心短按/长按操作
- 串口握手与保活
- Windows 端绝对音量控制
- Realtek 定向绑定
- 基本状态机稳定性修复
- 动画方向与触摸防抖修复

如需继续推进，后续可集中在：
- Windows 实机日志二次验收
- 若仍有少量触摸误判，再进一步收紧中心区判定与抬手滤波
- 恢复更高级的音量环渐变配色（在不引入错位的前提下）
