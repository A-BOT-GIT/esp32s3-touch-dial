# 06 Agent 可执行任务书集合

版本：v1.1

本文件中的任务可以直接复制给本地 Agent / Codex / Claude Code 执行。

---

# Task 0：冻结 no-force-encryption Consumer Control 诊断基线

```text
目标：冻结一个稳定的 Consumer Control BLE HID 工作状态，作为后续 Radial Controller 调试基线。

背景：
最新实机日志证明，关闭 BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT) 后：
- [BLE-HID] security: SC_BOND + IO_NONE
- [BLE-HID] force encryption level: disabled
- connected=2
- disconnected=0
- hid_sent=86
- hid_skip=0

这说明 BLE HID notify 到 Windows HID consumer 链路稳定。

执行步骤：
1. 确认当前状态满足：
   - force encryption level: disabled
   - BLE 连接稳定；
   - 旋转发送 volume_down / volume_up；
   - 短按发送 play_pause；
   - 长按发送 mute；
   - hid_sent > 0；
   - hid_skip = 0；
   - disconnected = 0 或显著减少；
   - 没有 BT_APPL / BT_BTM 错误刷屏。
2. 从该状态创建分支：
   git branch test/ble-consumer-volume-no-force-encrypt-working
3. 创建 tag：
   git tag ble-hid-no-force-encrypt-working
4. 添加文档 docs/diagnostics/consumer_volume_no_force_encrypt_baseline.md，说明该分支只用于 BLE HID 传输诊断，不是 Surface Dial 正式目标。
5. 不要修改正式 Radial 代码。
6. 输出：
   - 选用的 commit hash；
   - 分支名；
   - tag 名；
   - 证据日志摘要。
```

---

# Task 1：固化 no-force-encryption BLE 初始化策略

```text
目标：将 no-force-encryption 从实验结论固化为后续 BLE HID 主线初始化策略。

要求：
1. 保留：
   - BLESecurity
   - ESP_LE_AUTH_REQ_SC_BOND
   - ESP_IO_CAP_NONE
   - InitEncryptionKey / RespEncryptionKey
   - key size 16
   - CCCD 0x2902 权限补丁
   - ReportRef 0x2908 权限补丁
2. 默认禁用：
   BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)
3. 添加或确认编译开关：
   #define BLE_FORCE_ENCRYPTION_LEVEL 0
4. 只有 BLE_FORCE_ENCRYPTION_LEVEL=1 时才调用 setEncryptionLevel。
5. 启动日志必须打印：
   [BLE-HID] security: SC_BOND + IO_NONE
   [BLE-HID] force encryption level: disabled
6. 更新测试，确认默认状态不强制调用 setEncryptionLevel。
7. 编译并运行 pytest。
8. 不提交，输出验证报告。
```

---

# Task 2：创建 Radial Controller MVP 分支

```text
目标：从 no-force-encryption 稳定 BLE HOGP 基线创建正式 Surface Dial / Windows Radial Controller MVP 分支。

执行步骤：
1. 不要使用强制 setEncryptionLevel 的旧状态作为起点。
2. 使用稳定 BLE 初始化策略：
   - SC_BOND + IO_NONE
   - force encryption disabled
   - CCCD/ReportRef patched
   - DIS + adv services 1812/180F/180A
3. 创建分支：
   git checkout <no-force-encryption-stable-baseline>
   git checkout -b feature/ble-radial-controller-mvp
4. 清理 Consumer Control 代码：
   - 移除 MEDIA_REPORT_ID；
   - 移除 Consumer Control report map；
   - 移除 Volume Up/Down、Mute、Play/Pause 发送函数；
   - 移除 Mouse Wheel fallback；
   - 保留 BLE security、bonding、advertising、DIS、CCCD/2908 权限补丁；
   - 保留 no-force-encryption 策略。
5. 输出当前分支和清理摘要。
```

---

# Task 3：实现 Radial Controller Report Map 和 BLE report

```text
目标：实现最小 Windows Radial Controller HID over GATT 固件。

不要修改：
- BLE security；
- bonding 模式；
- advertising service UUID；
- DIS；
- CCCD/Report Reference 权限补丁；
- no-force-encryption 策略。

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
   [BLE-HID] security: SC_BOND + IO_NONE
   [BLE-HID] force encryption level: disabled
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

# Task 4：更新测试

```text
目标：为 Radial Controller MVP 添加/更新单元测试。

测试要求：
1. Report Map 包含：
   - 05 01
   - 09 0E
   - A1 01
   - 85 01
   - 05 0D
   - 09 21
   - A1 00
   - 05 09
   - 09 01
   - 05 01
   - 09 37
   - 75 0F
   - 81 06
   - C0 C0
2. Report Map 不包含:
   - Consumer Control 0x05 0x0C
   - Volume Increment 0xE9
   - Volume Decrement 0xEA
   - Mute 0xE2
   - Play/Pause 0xCD
3. buildRadialPayload 测试：
   - false, 0  -> 00 00
   - true, 0   -> 01 00
   - false, 1  -> 02 00
   - false, -1 -> FE FF
   - true, 1   -> 03 00
   - true, -1  -> FF FF
4. BLE report value 长度为 2，不包含 Report ID。
5. Report Reference 期望为 01 01。
6. 默认不调用 BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)。
7. 运行 pytest -q。
```

---

# Task 5：新增 Windows Radial Probe

```text
目标：新增 tools/win_radial_probe，用 Windows RadialController API 验证 ESP32 是否被系统当作 Radial Controller 消费。

要求：
1. 创建最小 Windows 测试程序，优先 C# UWP/WinUI。
2. 程序启动后创建 RadialController。
3. 添加自定义菜单项 ESP32 Probe。
4. 注册并显示事件：
   - RotationChanged
   - ButtonClicked
   - ControlAcquired / ControlLost，如 API 支持
   - 其他可用 radial events
5. UI 显示：
   - 最近事件日志；
   - rotation 累计值；
   - button 计数；
   - 清空按钮；
   - 导出日志按钮。
6. README 写清楚：
   - Windows 版本要求；
   - 如何打开项目；
   - 如何运行；
   - 如何配合 ESP32 测试。
7. 不要依赖 ESP32 源码编译。
```

---

# Task 6：Radial MVP 实机验证

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

收集：
1. summary.txt
2. serial_timestamped.log
3. Windows Radial Probe 日志
4. 截图，如有菜单弹出

判定：
- 如果连接反复断开，先查 BLE_FORCE_ENCRYPTION_LEVEL 是否为 0，再查 identity/cache。
- 如果 hid=sent 但 probe 无事件，查 Report Map / Report Reference / report payload。
- 如果 probe 有 rotation 但菜单不弹，查 button hold。
```

---

# Task 7：不要把 Consumer Control 当作 Surface Dial 完成

```text
当前 no-force-encryption Consumer Control 分支可以作为 BLE HID 诊断基线：
- volume_down
- volume_up
- play_pause
- mute

但它不是 Surface Dial。

Surface Dial 正式分支必须：
- 移除 Consumer Control usages；
- 使用 System Multi-Axis Controller；
- 使用 Button + Dial；
- 使用 2 字节 radial payload；
- 使用 Windows Radial Probe 验证 RotationChanged / Button。
```
