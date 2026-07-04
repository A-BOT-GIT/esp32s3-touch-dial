# 06 Agent 可执行任务书集合

本文件中的任务可以直接复制给本地 Agent / Codex / Claude Code 执行。

---

# Task 0：冻结 Consumer Control 诊断基线

```text
目标：冻结一个稳定的 Consumer Control BLE HID 工作状态，作为后续 Radial Controller 调试基线。

背景：
前期 Consumer Control 分支已证明 Windows 能消费 ESP32 BLE HID 媒体键。短按曾被识别成 Mute，说明 BLE HID notify 到 Windows HID 消费链路是通的。

不要从当前 B+C 连接抖动状态创建 tag。

执行步骤：
1. 查看 git 历史和工作区，找到最近一次满足以下条件的状态：
   - BLE 连接稳定；
   - 旋转发送 data=01 / data=02；
   - 短按发送 data=04；
   - Windows 能响应媒体键；
   - hid_sent > 0；
   - hid_skip = 0；
   - 没有大量 connected/disconnected 刷屏。
2. 从该状态创建分支：
   git branch test/ble-consumer-volume-working
3. 创建 tag：
   git tag ble-hid-consumer-working
4. 添加文档 docs/diagnostics/consumer_volume_baseline.md，说明该分支只用于 BLE HID 传输诊断，不是 Surface Dial 正式目标。
5. 不要修改正式 Radial 代码。
6. 输出：
   - 选用的 commit hash；
   - 分支名；
   - tag 名；
   - 证据日志摘要。
```

---

# Task 1：创建 Radial Controller MVP 分支

```text
目标：从稳定 BLE HOGP 基线创建正式 Surface Dial / Windows Radial Controller MVP 分支。

执行步骤：
1. 不要使用当前 B+C 断连工作区作为起点。
2. 找到稳定 BLE HOGP 基线：
   - BLE advertising 正常；
   - Windows 能连接；
   - HID over GATT 枚举正常；
   - 连接 2 分钟内不大量断开。
3. 创建分支：
   git checkout <stable-baseline>
   git checkout -b feature/ble-radial-controller-mvp
4. 清理 Consumer Control 代码：
   - 移除 MEDIA_REPORT_ID；
   - 移除 Consumer Control report map；
   - 移除 Volume Up/Down、Mute、Play/Pause 发送函数；
   - 移除 Mouse Wheel fallback；
   - 保留 BLE security、bonding、advertising、DIS、CCCD/2908 权限补丁。
5. 输出当前分支和清理摘要。
```

---

# Task 2：实现 Radial Controller Report Map 和 BLE report

```text
目标：实现最小 Windows Radial Controller HID over GATT 固件。

不要修改：
- BLE security；
- bonding 模式；
- advertising service UUID；
- DIS；
- CCCD/Report Reference 权限补丁。

实现要求：
1. 定义 RADIAL_REPORT_ID = 1。
2. 定义 radialControllerReportMap：
   - Top-level: Generic Desktop / System Multi-Axis Controller
   - Report ID 1
   - Physical collection: Digitizers / Puck
   - Button Page / Button 1，1 bit，Data Var Abs
   - Generic Desktop / Dial，15 bit，Data Var Rel
   - Dial 带 Unit Exponent -1、Unit Degrees、Logical/Physical -3600..3600
3. 只创建一个 input report：
   bleRadialInputReport = bleDialHid->inputReport(RADIAL_REPORT_ID)
4. 对 bleRadialInputReport 调用 fixHogpInputReportPermissions()。
5. Report Reference 应为 01 01。
6. BLE notify value 不包含 Report ID，只发 2 字节。
7. 实现 buildRadialPayload(bool pressed, int16_t delta)：
   - bit0 button
   - bit1-15 signed 15-bit dial delta
8. 实现 sendRadialReport(bool pressed, int16_t delta)。
9. 日志：
   [BLE-HID] radial report id: 1
   [BLE-HID] radial report map size: N
   [BLE-HID] radial report ref: 01 01
   >BLE radial report len=2 data=XX XX button=B delta=D hid=sent
10. 编码器右转发送 +1 或 +10。
11. 编码器左转发送 -1 或 -10。
12. 按下发送 button=1 delta=0。
13. 释放发送 button=0 delta=0。
14. 长按不发送媒体键，只保持 button=1。
```

---

# Task 3：更新测试

```text
目标：为 Radial Controller MVP 添加/更新单元测试。

测试要求：
1. Report Map 包含：05 01, 09 0E, A1 01, 85 01, 05 0D, 09 21, A1 00, 05 09, 09 01, 05 01, 09 37, 75 0F, 81 06, C0 C0。
2. Report Map 不包含：Consumer Control 0x05 0x0C, Volume Increment 0xE9, Volume Decrement 0xEA, Mute 0xE2, Play/Pause 0xCD。
3. buildRadialPayload 测试：false,0->00 00；true,0->01 00；false,1->02 00；false,-1->FE FF；true,1->03 00；true,-1->FF FF。
4. BLE report value 长度为 2，不包含 Report ID。
5. Report Reference 期望为 01 01。
6. 运行 pytest -q。
```

---

# Task 4：新增 Windows Radial Probe

```text
目标：新增 tools/win_radial_probe，用 Windows RadialController API 验证 ESP32 是否被系统当作 Radial Controller 消费。

要求：
1. 创建最小 Windows 测试程序，优先 C# UWP/WinUI。
2. 程序启动后创建 RadialController。
3. 添加自定义菜单项 ESP32 Probe。
4. 注册并显示事件：RotationChanged、ButtonClicked、ControlAcquired / ControlLost，如 API 支持。
5. UI 显示最近事件日志、rotation 累计值、button 计数、清空按钮、导出日志按钮。
6. README 写清楚 Windows 版本要求、如何打开项目、如何运行、如何配合 ESP32 测试。
7. 不要依赖 ESP32 源码编译。
```

---

# Task 5：Radial MVP 实机验证

```text
目标：验证 feature/ble-radial-controller-mvp 是否能作为 Windows Radial Controller 工作。

准备：
1. 烧录 feature/ble-radial-controller-mvp。
2. 连接新设备名，例如 ESP32-S3 Radial MVP。
3. 打开串口抓取脚本。
4. 打开 Windows Radial Probe。

操作：
1. 静置 30 秒，观察是否断连。
2. 右转 5 格。
3. 左转 5 格。
4. 短按 3 次。
5. 长按 2 秒释放。
6. 菜单打开时旋转。

收集：summary.txt、serial_timestamped.log、Windows Radial Probe 日志、截图。

判定：如果连接反复断开，先查 identity/cache；如果 hid=sent 但 probe 无事件，查 Report Map / Report Reference / report payload；如果 probe 有 rotation 但菜单不弹，查 button hold。
```

---

# Task 6：不要提交失败工作区

```text
当前 B+C Consumer Control 分支出现连接抖动：connected 很多，disconnected 很多，hid_sent=0，hid_skip>0。

不要提交该工作区。
不要基于它继续做 Radial MVP。
只保留为失败案例。
输出 git diff 摘要后等待人工确认。
```
