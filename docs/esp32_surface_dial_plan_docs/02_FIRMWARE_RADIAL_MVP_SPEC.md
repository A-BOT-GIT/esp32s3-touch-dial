# 02 ESP32 固件侧 Radial Controller MVP 详细实现规范

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

## 2. 固件目标

实现一个最小 Windows Radial Controller BLE HID 设备。

不要实现：Consumer Control 音量键、Play/Pause、Mute、Mouse Wheel、Joystick、Generic X/Y、Haptic output、on-screen position。

MVP 只做 Button + Dial。

## 3. 常量定义

```cpp
constexpr uint8_t RADIAL_REPORT_ID = 1;
constexpr int16_t RADIAL_DELTA_UNIT = 1;   // 0.1 degree, first try
```

如旋转太慢，可测试：

```cpp
constexpr int16_t RADIAL_DELTA_UNIT = 10;  // 1.0 degree
```

## 4. Report Descriptor

### 4.1 目标结构

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

### 4.2 建议 Report Map

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

## 5. BLE HID 初始化

只创建一个 Radial input report：

```cpp
BLECharacteristic* bleRadialInputReport = nullptr;
bleRadialInputReport = bleDialHid->inputReport(RADIAL_REPORT_ID);
fixHogpInputReportPermissions(bleRadialInputReport);
```

禁止创建 `MEDIA_REPORT_ID` 或旧 `DIAL_REPORT_ID` 的 input report。

## 6. BLE Report Reference

期望：

```text
Report Reference descriptor 0x2908 = 01 01
```

启动日志必须打印：

```text
[BLE-HID] radial report id: 1
[BLE-HID] radial report ref: 01 01
```

## 7. BLE notify value 规则

BLE HOGP `inputReport(REPORT_ID)` 的 characteristic value 不要包含 Report ID。

错误：

```text
01 FE FF
```

正确：

```text
FE FF
```

## 8. payload 编码

### 8.1 位布局

```text
uint16_t payload
bit0      = button
bit1-15   = signed 15-bit dial delta
```

### 8.2 参考实现

```cpp
static uint16_t buildRadialPayload(bool pressed, int16_t deltaTenthsDegree) {
  int16_t d = constrain(deltaTenthsDegree, -3600, 3600);
  uint16_t dial15 = ((uint16_t)d) & 0x7FFF;
  return (uint16_t)((dial15 << 1) | (pressed ? 1 : 0));
}
```

### 8.3 发送函数

```cpp
static bool sendRadialReport(bool pressed, int16_t deltaTenthsDegree) {
  if (!bleDialConnected || !bleRadialInputReport) {
    Serial.printf(
      ">BLE radial report skip button=%d delta=%d connected=%d report=%d
",
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
    ">BLE radial report len=2 data=%02X %02X button=%d delta=%d hid=sent
",
    report[0], report[1], pressed ? 1 : 0, deltaTenthsDegree
  );

  return true;
}
```

## 9. 编码器事件映射

旋转：

```cpp
if (delta > 0) sendRadialReport(buttonPressed, +RADIAL_DELTA_UNIT);
else if (delta < 0) sendRadialReport(buttonPressed, -RADIAL_DELTA_UNIT);
```

按下 / 释放：

```cpp
onButtonDown:
  buttonPressed = true;
  sendRadialReport(true, 0);

onButtonUp:
  buttonPressed = false;
  sendRadialReport(false, 0);
```

长按不需要固件直接发特殊媒体键。Surface Dial 菜单应由 Windows 对 button hold 的解释产生。

## 10. 启动日志

```text
[BLE-HID] init start
[BLE-HID] security: SC_BOND + IO_NONE + ENC
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

## 11. 测试

### 11.1 描述符测试

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

### 11.2 payload 测试

| 输入 | 期望 bytes |
|---|---|
| pressed=false, delta=0 | `00 00` |
| pressed=true, delta=0 | `01 00` |
| pressed=false, delta=1 | `02 00` |
| pressed=false, delta=-1 | `FE FF` |
| pressed=true, delta=1 | `03 00` |
| pressed=true, delta=-1 | `FF FF` |

### 11.3 BLE report 规则测试

检查：BLE report value 长度为 2；不包含 Report ID；Report Reference 为 `01 01`；不存在 Consumer Control usages。

## 12. 验收日志

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
