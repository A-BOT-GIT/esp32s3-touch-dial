# 02 ESP32 固件侧 Radial Controller MVP 详细实现规范

版本：v1.2

## 1. 文件范围

主文件：

```text
esp32s3_touch_dial.ino
```

可能涉及测试：

```text
tests/test_ble_backend_init_order.py
tests/test_hid_capture_analysis.py
tools/analyze_hid_captures.py
```

---

## 2. 固件目标

实现一个最小 Windows Radial Controller BLE HID 设备。

不要实现：

- Consumer Control 音量键；
- Play/Pause；
- Mute；
- Mouse Wheel；
- Joystick；
- Generic X/Y；
- Haptic output；
- on-screen position。

MVP 只做 Button + Dial。

---

## 3. BLE 初始化策略

### 3.1 必须保留

```cpp
BLESecurity* bleSecurity = new BLESecurity();
bleSecurity->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
bleSecurity->setCapability(ESP_IO_CAP_NONE);
bleSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
bleSecurity->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
bleSecurity->setKeySize(16);
```

### 3.2 默认禁止强制加密级别

不要默认调用：

```cpp
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
```

推荐：

```cpp
#ifndef BLE_FORCE_ENCRYPTION_LEVEL
#define BLE_FORCE_ENCRYPTION_LEVEL 0
#endif

#if BLE_FORCE_ENCRYPTION_LEVEL
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
#endif
```

启动日志：

```text
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
```

### 3.3 保留权限补丁

继续保留：

```cpp
fixHogpInputReportPermissions(bleRadialInputReport);
```

预期：

```text
2908=yes
2902=yes
```

---

## 4. 常量定义

建议：

```cpp
constexpr uint8_t RADIAL_REPORT_ID = 1;
constexpr int16_t RADIAL_DELTA_UNIT = 1;   // 0.1 degree, first try
```

如旋转太慢，可测试：

```cpp
constexpr int16_t RADIAL_DELTA_UNIT = 10;  // 1.0 degree
```

---

## 5. Report Descriptor

### 5.1 目标结构

```text
Usage Page (Generic Desktop)
Usage (System Multi-Axis Controller)
Collection (Application)
  Report ID 1
  Usage Page (Digitizers)
  Usage (Puck)
  Collection (Physical)
    Usage Page (Button)
    Usage Button 1
    1-bit input
    Usage Page (Generic Desktop)
    Usage Dial
    15-bit relative input
  End Physical
End Application
```

### 5.2 建议 Report Map

```cpp
static const uint8_t radialControllerReportMap[] = {
  0x05, 0x01,        // Usage Page (Generic Desktop)
  0x09, 0x0E,        // Usage (System Multi-Axis Controller)
  0xA1, 0x01,        // Collection (Application)

  0x85, RADIAL_REPORT_ID, // Report ID (1)

  0x05, 0x0D,        // Usage Page (Digitizers)
  0x09, 0x21,        // Usage (Puck)
  0xA1, 0x00,        // Collection (Physical)

  0x05, 0x09,        // Usage Page (Button)
  0x09, 0x01,        // Usage (Button 1)
  0x95, 0x01,        // Report Count (1)
  0x75, 0x01,        // Report Size (1)
  0x15, 0x00,        // Logical Minimum (0)
  0x25, 0x01,        // Logical Maximum (1)
  0x81, 0x02,        // Input (Data, Var, Abs)

  0x05, 0x01,        // Usage Page (Generic Desktop)
  0x09, 0x37,        // Usage (Dial)
  0x95, 0x01,        // Report Count (1)
  0x75, 0x0F,        // Report Size (15)
  0x55, 0x0F,        // Unit Exponent (-1)
  0x65, 0x14,        // Unit (Degrees, English Rotation)
  0x36, 0xF0, 0xF1,  // Physical Minimum (-3600)
  0x46, 0x10, 0x0E,  // Physical Maximum (3600)
  0x16, 0xF0, 0xF1,  // Logical Minimum (-3600)
  0x26, 0x10, 0x0E,  // Logical Maximum (3600)
  0x81, 0x06,        // Input (Data, Var, Rel)

  0xC0,              // End Collection (Physical)
  0xC0               // End Collection (Application)
};
```

---

## 6. BLE HID 初始化

### 6.1 只创建一个 Radial input report

```cpp
BLECharacteristic* bleRadialInputReport = nullptr;
```

初始化时：

```cpp
bleRadialInputReport = bleDialHid->inputReport(RADIAL_REPORT_ID);
fixHogpInputReportPermissions(bleRadialInputReport);
```

禁止：

```cpp
bleDialHid->inputReport(MEDIA_REPORT_ID);
bleDialHid->inputReport(DIAL_REPORT_ID);
```

除非它就是同一个 `RADIAL_REPORT_ID`。

---

## 7. BLE Report Reference

期望：

```text
Report Reference descriptor 0x2908 = 01 01
```

含义：

```text
Report ID = 1
Report Type = Input Report
```

启动日志必须打印：

```text
[BLE-HID] radial report id: 1
[BLE-HID] radial report ref: 01 01
```

---

## 8. BLE notify value 规则

重要：

```text
BLE HOGP inputReport(REPORT_ID) 的 characteristic value 不要包含 Report ID。
```

所以 Radial report value 是 2 字节，不是 3 字节。

错误：

```text
01 FE FF
```

正确：

```text
FE FF
```

---

## 9. payload 编码

### 9.1 位布局

```text
uint16_t payload

bit0      = button
bit1-15   = signed 15-bit dial delta
```

### 9.2 参考实现

```cpp
static uint16_t buildRadialPayload(bool pressed, int16_t deltaTenthsDegree) {
  int16_t d = constrain(deltaTenthsDegree, -3600, 3600);
  uint16_t dial15 = ((uint16_t)d) & 0x7FFF;
  return (uint16_t)((dial15 << 1) | (pressed ? 1 : 0));
}
```

### 9.3 发送函数

```cpp
static bool sendRadialReport(bool pressed, int16_t deltaTenthsDegree) {
  if (!bleDialConnected || !bleRadialInputReport) {
    Serial.printf(
      ">BLE radial report skip button=%d delta=%d connected=%d report=%d\n",
      pressed ? 1 : 0,
      deltaTenthsDegree,
      bleDialConnected ? 1 : 0,
      bleRadialInputReport ? 1 : 0
    );
    return false;
  }

  uint16_t payload = buildRadialPayload(pressed, deltaTenthsDegree);

  uint8_t report[2] = {
    (uint8_t)(payload & 0xFF),
    (uint8_t)((payload >> 8) & 0xFF)
  };

  bleRadialInputReport->setValue(report, sizeof(report));
  bleRadialInputReport->notify();

  Serial.printf(
    ">BLE radial report len=2 data=%02X %02X button=%d delta=%d hid=sent\n",
    report[0],
    report[1],
    pressed ? 1 : 0,
    deltaTenthsDegree
  );

  return true;
}
```

---

## 10. 编码器事件映射

### 10.1 旋转

```cpp
if (delta > 0) {
  sendRadialReport(buttonPressed, +RADIAL_DELTA_UNIT);
} else if (delta < 0) {
  sendRadialReport(buttonPressed, -RADIAL_DELTA_UNIT);
}
```

### 10.2 按下 / 释放

不要把按键变成 mute/play/pause。

```cpp
onButtonDown:
  buttonPressed = true;
  sendRadialReport(true, 0);

onButtonUp:
  buttonPressed = false;
  sendRadialReport(false, 0);
```

### 10.3 长按

长按不需要固件直接发特殊媒体键。Surface Dial 菜单应由 Windows 对 button hold 的解释产生。

固件只需要保持：

```text
button = 1
```

直到释放。

---

## 11. 启动日志

启动阶段必须打印：

```text
[BLE-HID] init start
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
[BLE-HID] address: XX:XX:XX:XX:XX:XX
[BLE-HID] radial report id: 1
[BLE-HID] radial report map size: <N>
[BLE-HID] radial input report created
[BLE-HID] radial report ref: 01 01
[BLE-HID] descriptor permissions patched: 2908=yes, 2902=yes
[BLE-HID] services started
[BLE-HID] adv services: 1812,180F,180A
[BLE-HID] advertising started
```

---

## 12. 测试

### 12.1 描述符测试

检查字节序列包含：

```text
05 01
09 0E
A1 01
85 01
05 0D
09 21
A1 00
05 09
09 01
05 01
09 37
75 0F
81 06
C0 C0
```

### 12.2 payload 测试

| 输入 | 期望 bytes |
|---|---|
| pressed=false, delta=0 | `00 00` |
| pressed=true, delta=0 | `01 00` |
| pressed=false, delta=1 | `02 00` |
| pressed=false, delta=-1 | `FE FF` |
| pressed=true, delta=1 | `03 00` |
| pressed=true, delta=-1 | `FF FF` |

### 12.3 BLE report 规则测试

检查：

- BLE report value 长度为 2；
- 不包含 Report ID；
- Report Reference 为 `01 01`；
- 不存在 Consumer Control usages；
- 不存在 Media Report ID；
- 不存在 Mouse Wheel fallback；
- 不默认启用 `BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)`。

---

## 13. 编译命令

根据项目实际环境执行：

```bash
arduino-cli compile --fqbn esp32:esp32:esp32s3 .
```

USB+CDC 版本按项目现有命令执行。

测试：

```bash
pytest -q
```

---

## 14. 验收日志

旋转右：

```text
>BLE radial report len=2 data=02 00 button=0 delta=1 hid=sent
```

旋转左：

```text
>BLE radial report len=2 data=FE FF button=0 delta=-1 hid=sent
```

按下：

```text
>BLE radial report len=2 data=01 00 button=1 delta=0 hid=sent
```

释放：

```text
>BLE radial report len=2 data=00 00 button=0 delta=0 hid=sent
```


---

# v1.2 技术细节补充索引

本文件保留核心规范。更细的实现细节拆到以下文件：

```text
10_TECHNICAL_IMPLEMENTATION_DETAILS.md
11_HID_DESCRIPTOR_AND_PAYLOAD_DETAILS.md
12_ENCODER_BUTTON_STATE_MACHINE.md
```

Agent 实施时应同时阅读上述文件，尤其是：

```text
- BLE 初始化调用顺序
- ReportRef / CCCD patch 时机
- Radial 2-byte payload 构造
- 按键按下/释放状态机
- long press 不再映射为 Consumer Mute
```
