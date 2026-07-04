# 14 Agent 详细实施任务书

版本：v1.2

本文件比 `06_AGENT_TASKS.md` 更偏代码级实现，适合直接给 agent 执行。

---

# Task A：固化 BLE no-force-encryption 策略

```text
目标：
把最新验证成功的 BLE 初始化策略固化到项目中。

必须保留：
- SC_BOND
- IO_NONE
- InitEncryptionKey / RespEncryptionKey
- key size 16
- CCCD / ReportRef 权限 patch

必须默认禁用：
- BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)

实施：
1. 搜索 BLEDevice::setEncryptionLevel。
2. 用 BLE_FORCE_ENCRYPTION_LEVEL 编译开关包住。
3. 默认值为 0。
4. 启动日志打印：
   [BLE-HID] force encryption level: disabled
5. 添加测试确认默认不开启。
6. 编译 BLE、USB+CDC、pytest。
7. 输出 diff 摘要。
```

---

# Task B：清理 Media Dial，准备 Radial MVP

```text
目标：
在 feature/ble-radial-controller-mvp 分支中移除 Consumer Control / Media Dial。

删除或隔离：
- MEDIA_REPORT_ID
- mediaReportMap
- sendVolumeUp()
- sendVolumeDown()
- sendPlayPause()
- sendMute()
- bleMediaInputReport
- action=volume_up / volume_down / play_pause / mute 的日志路径

不要删除：
- BLE 初始化
- no-force-encryption 策略
- stable address
- DIS
- advertising
- Battery service
- HID service
- fixHogpInputReportPermissions()

输出：
- 哪些符号被移除
- 是否还存在 Consumer Control usage 0x0C
```

---

# Task C：添加 Radial Descriptor

```text
目标：
实现 radialControllerReportMap。

要求：
1. 新增 RADIAL_REPORT_ID=1。
2. 新增 radialControllerReportMap。
3. 包含：
   - 05 01 / 09 0E / A1 01
   - 85 01
   - 05 0D / 09 21 / A1 00
   - Button 1
   - Dial 0x37
   - 15-bit
   - Relative input 81 06
   - C0 C0
4. reportMap() 使用 radialControllerReportMap。
5. 日志打印 report map size。
6. 单元测试检查关键字节序列。
```

---

# Task D：添加 Radial Input Report Characteristic

```text
目标：
HOGP 只创建一个 Radial Input Report。

要求：
1. 定义：
   BLECharacteristic* bleRadialInputReport = nullptr;
2. beginDialBackend() 中：
   bleRadialInputReport = bleDialHid->inputReport(RADIAL_REPORT_ID);
3. 调用：
   fixHogpInputReportPermissions(bleRadialInputReport);
4. 日志：
   [BLE-HID] radial input report created
   [BLE-HID] radial report ref: 01 01
5. 确认不再创建 MEDIA_REPORT_ID=2。
6. 单元测试检查 ReportRef=01 01。
```

---

# Task E：实现 buildRadialPayload()

```text
目标：
实现 Button + 15-bit signed Dial 的 payload packing。

函数：
uint16_t buildRadialPayload(bool pressed, int16_t deltaTenthsDegree)

规则：
- clamp delta 到 -3600..3600
- dial15 = ((uint16_t)delta) & 0x7FFF
- payload = (dial15 << 1) | button

测试：
false,0   -> 00 00
true,0    -> 01 00
false,1   -> 02 00
false,-1  -> FE FF
true,1    -> 03 00
true,-1   -> FF FF
false,10  -> 14 00
false,-10 -> EC FF
```

---

# Task F：实现 sendRadialReport()

```text
目标：
发送 BLE HOGP Radial Input Report。

要求：
1. 函数签名：
   bool sendRadialReport(bool pressed, int16_t delta)
2. 若未连接，打印 skip reason=not_connected。
3. 若 characteristic 为空，打印 skip reason=no_report。
4. 正常时：
   - buildRadialPayload
   - 写入 2 字节 little-endian
   - setValue(report, 2)
   - notify()
5. 日志：
   >BLE radial report len=2 data=XX XX button=B delta=D hid=sent
6. 不带 Report ID。
7. 更新 last_send_type。
```

---

# Task G：改编码器旋转路径

```text
目标：
把旋转从 Media Dial 映射改为 Radial Dial delta。

实现：
1. 定义 radialButtonPressed 全局状态。
2. 旋转右：
   sendRadialReport(radialButtonPressed, +RADIAL_DELTA_UNIT)
3. 旋转左：
   sendRadialReport(radialButtonPressed, -RADIAL_DELTA_UNIT)
4. 日志：
   >ENC rotate dir=RIGHT button=0 radial_delta=1 hid=sent
   >ENC rotate dir=LEFT button=0 radial_delta=-1 hid=sent
5. 不再改变内部 volume 作为主逻辑。
   如果保留 volume UI，只能作为 debug，不影响 HID。
```

---

# Task H：改按键路径

```text
目标：
按键只发送 Radial button，不发送媒体键。

实现：
1. button down:
   radialButtonPressed = true
   sendRadialReport(true, 0)
2. button up:
   radialButtonPressed = false
   sendRadialReport(false, 0)
3. long press:
   只打印 hold candidate，不发送 mute。
4. 删除/禁用短按 play_pause。
5. 删除/禁用长按 mute。
6. 日志：
   >ENC_BUTTON down hid=sent
   >ENC_BUTTON up held_ms=... hid=sent
   >ENC_BUTTON hold candidate for radial menu
```

---

# Task I：更新设备 identity

```text
目标：
避免 Windows 继续使用 Media Dial 的 GATT/HID 缓存。

要求：
1. 设备名：
   ESP32-S3 Radial MVP
2. BLE_IDENTITY_SUFFIX：
   0x31
3. 启动日志完整打印 6 字节地址。
4. 如果后续改 descriptor，再改到：
   ESP32-S3 Radial MVP2
   0x32
```

---

# Task J：实机验证脚本输出适配

```text
目标：
让现有串口抓取/分析脚本识别 radial report。

匹配新增：
- BLE radial report
- radial report len=2
- button=
- delta=
- action 不再是 media action
- force encryption level

统计新增：
- radial_report
- radial_button_down
- radial_button_up
- radial_rotate_positive
- radial_rotate_negative
- force_encryption_disabled

避免误报：
- last_backend_error=none 不算 error
```

---

# Task K：Windows Radial Probe

```text
目标：
新增 tools/win_radial_probe。

最小要求：
1. C# UWP/WinUI 工程。
2. 创建 RadialController。
3. 添加 ESP32 Probe 菜单项。
4. 打印：
   - RotationChanged
   - ButtonClicked
   - ControlAcquired
   - ControlLost
5. README 写清运行步骤。
6. 不阻塞固件编译。
```

---

# Task L：最终验证报告

```text
目标：
执行 Radial MVP 端到端验证。

报告必须包含：
1. 分支名
2. commit hash
3. BLE identity
4. force encryption level
5. Report ID
6. ReportRef
7. Report map size
8. 编译结果
9. pytest 结果
10. 串口 summary：
    - connected
    - disconnected
    - hid_sent
    - hid_skip
    - real BT errors
11. 关键日志：
    - 右转
    - 左转
    - 按下
    - 释放
    - 长按
12. Windows Radial Probe 结果：
    - RotationChanged right
    - RotationChanged left
    - Button event
    - long press/menu
13. PASS/FAIL
14. 下一步建议
```
