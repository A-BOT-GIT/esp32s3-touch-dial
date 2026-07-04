# 01 后续总体路线图

版本：v1.2

## 总体策略

项目分为 7 个阶段：

1. 冻结 no-force-encryption Consumer Control 诊断基线；
2. 将 no-force-encryption 固化为 BLE HID 主线初始化策略；
3. 新建正式 Radial Controller MVP 分支；
4. 实现固件侧最小 Radial HID 描述符和 2 字节报告；
5. 建立 Windows Radial Probe；
6. 做端到端验证与故障分流；
7. 增强 haptic / on-screen / 外观体验。

---

## Phase 0：冻结 no-force-encryption Consumer Control 基线

### 目标

保留一个“Windows 确实能稳定消费 ESP32 BLE HID 报告”的工作状态，后续 Radial 分支调坏时可以回归对照。

### 基线必须满足

```text
SC_BOND + IO_NONE
force encryption level: disabled
完整 BLE address 打印
ReportRef 正确
BLE 连接稳定
hid_sent > 0
hid_skip = 0
disconnected = 0 或显著减少
```

### 建议操作

```bash
git branch test/ble-consumer-volume-no-force-encrypt-working
git tag ble-hid-no-force-encrypt-working
```

### 作用

这个分支只用作诊断：

```text
证明 BLE HID notify -> Windows HID consumer 链路是通的。
```

它不是 Surface Dial 正式主线。

---

## Phase 1：固化 BLE 初始化策略

### 目标

把最新实测成功的 BLE 初始化策略作为后续 Radial Controller 的底座。

### 策略

```text
保留 BLESecurity
保留 SC_BOND
保留 IO_NONE
保留 InitEncryptionKey / RespEncryptionKey
保留 key size 16
保留 CCCD / ReportRef 权限补丁
默认禁用 BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)
```

### 推荐代码

```cpp
#ifndef BLE_FORCE_ENCRYPTION_LEVEL
#define BLE_FORCE_ENCRYPTION_LEVEL 0
#endif

#if BLE_FORCE_ENCRYPTION_LEVEL
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
#endif

Serial.printf("[BLE-HID] force encryption level: %s\n",
              BLE_FORCE_ENCRYPTION_LEVEL ? "enabled" : "disabled");
```

---

## Phase 2：从 no-force-encryption 基线创建 Radial MVP 分支

### 分支命名

```bash
git checkout <no-force-encryption-stable-baseline>
git checkout -b feature/ble-radial-controller-mvp
```

### 禁止事项

- 不要回到强制 `setEncryptionLevel`；
- 不要混入 Consumer Control；
- 不要做 haptic；
- 不要做 on-screen coordinate；
- 不要在第一版里同时支持多种 HID report；
- 不要让 Windows 继续吃旧缓存。

---

## Phase 3：固件 Radial Controller MVP

### MVP 输入

| 输入 | HID Usage |
|---|---|
| Button | Button Page / Button 1 |
| Dial | Generic Desktop / Dial |

### MVP 报告

BLE notify value：

```text
2 bytes:
bit0      = button
bit1-15   = signed 15-bit dial delta
```

### 示例

| 动作 | BLE notify value |
|---|---|
| 无输入 | `00 00` |
| 按下 | `01 00` |
| 释放 | `00 00` |
| 顺时针 +1 | `02 00` |
| 逆时针 -1 | `FE FF` |

---

## Phase 4：Windows Radial Probe

### 为什么需要 Probe

Surface Dial 不等于音量键。正式验证必须看 Windows RadialController API 是否收到事件。

### Probe 功能

- 打开一个测试窗口；
- 创建 RadialController；
- 添加 `ESP32 Probe` 菜单项；
- 打印 `ButtonClicked`；
- 打印 `RotationChanged`；
- 打印菜单/控制权事件；
- 输出文本日志。

---

## Phase 5：端到端验证

验证顺序：

1. Windows 识别新设备名；
2. BLE 连接稳定 2 分钟；
3. 串口看到 radial report；
4. Probe 收到 rotation；
5. Probe 收到 button click；
6. 长按能触发 radial menu；
7. 菜单打开时旋转能切换菜单项；
8. 菜单关闭时旋转能执行当前工具动作。

---

## Phase 6：故障分流

### A. 设备连接不稳定

优先查：

- 是否意外启用了 `BLE_FORCE_ENCRYPTION_LEVEL=1`；
- Windows 缓存；
- BLE 地址和设备名是否变化；
- Report ID / Report Reference 是否实际一致；
- 是否有旧 input report characteristic；
- 是否错误重启 advertising；
- 是否过早或重复调用 encryption。

### B. 连接稳定但 Windows 不识别 Radial

优先查：

- Report Map；
- Top-level collection；
- Mandatory usages；
- Report Reference；
- BLE notify 是否多塞 Report ID；
- Report payload bit packing。

### C. Windows 识别但旋转没事件

优先查：

- Dial 是否是 Relative；
- delta 是否非零；
- delta 符号方向；
- 单位和 logical range；
- Windows Probe 是否拥有焦点。

---

## Phase 7：完整 Surface Dial 增强

MVP 成功后再考虑：

| 功能 | 优先级 |
|---|---|
| haptic output | 中 |
| on-screen contact X/Y | 低 |
| 模式切换 | 中 |
| 屏幕 UI 显示当前状态 | 中 |
| 低功耗和自动重连 | 中 |
| 外壳和手感 | 后期 |

---

## 最新推荐路线

```text
Phase 0：冻结 no-force-encryption Consumer Control 稳定基线
Phase 1：把 no-force-encryption 写成正式 BLE 初始化策略
Phase 2：从该策略创建 feature/ble-radial-controller-mvp
Phase 3：替换 Media Report 为 Radial Controller Report
Phase 4：实现 2 字节 radial payload，不带 Report ID
Phase 5：Windows Radial Probe 验证 RotationChanged / Button
Phase 6：再做菜单、长按、haptic、on-screen
```


---

# v1.2 技术实施顺序补充

## 技术实施顺序

正式进入 `feature/ble-radial-controller-mvp` 后，建议按这个顺序写代码：

```text
1. 固化 BLE 初始化策略
   - SC_BOND + IO_NONE
   - BLE_FORCE_ENCRYPTION_LEVEL=0
   - 完整地址日志
   - 1812/180F/180A advertising
   - DIS 保留

2. 清理 Consumer Control
   - 删除 MEDIA_REPORT_ID
   - 删除 mediaReportMap
   - 删除 volume_up / volume_down / play_pause / mute 发送函数
   - 删除 1-byte media report 逻辑

3. 添加 Radial descriptor
   - RADIAL_REPORT_ID=1
   - System Multi-Axis Controller
   - Puck physical collection
   - Button 1 + Dial
   - ReportRef=01 01

4. 添加 radial payload 构造函数
   - bit0 = button
   - bit1-15 = signed 15-bit delta
   - BLE value = 2 bytes
   - 不带 Report ID

5. 改编码器事件路径
   - rotate -> sendRadialReport(buttonState, delta)
   - button down -> sendRadialReport(true, 0)
   - button up -> sendRadialReport(false, 0)
   - long press 不发媒体键

6. 添加测试
   - descriptor byte sequence
   - payload packing
   - no Consumer Control
   - no forced encryption
   - ReportRef=01 01

7. 实机测试
   - 先只看连接稳定和 hid=sent
   - 再看 Windows Radial Probe
```

详细实现请看：

```text
10_TECHNICAL_IMPLEMENTATION_DETAILS.md
11_HID_DESCRIPTOR_AND_PAYLOAD_DETAILS.md
12_ENCODER_BUTTON_STATE_MACHINE.md
13_WINDOWS_RADIAL_PROBE_IMPLEMENTATION.md
14_AGENT_IMPLEMENTATION_TASKS_DETAILED.md
```
