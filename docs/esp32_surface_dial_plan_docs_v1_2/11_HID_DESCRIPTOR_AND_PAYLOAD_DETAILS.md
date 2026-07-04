# 11 HID Descriptor 与 Payload 字节级细节

版本：v1.2

## 1. Radial Controller Report Descriptor 目标

Radial MVP 的 descriptor 目标是让 Windows 看到：

```text
Generic Desktop / System Multi-Axis Controller
  Digitizers / Puck
    Button 1
    Dial relative
```

---

## 2. Descriptor 字节表

| 字节 | 含义 |
|---|---|
| `05 01` | Usage Page = Generic Desktop |
| `09 0E` | Usage = System Multi-Axis Controller |
| `A1 01` | Collection = Application |
| `85 01` | Report ID = 1 |
| `05 0D` | Usage Page = Digitizers |
| `09 21` | Usage = Puck |
| `A1 00` | Collection = Physical |
| `05 09` | Usage Page = Button |
| `09 01` | Usage = Button 1 |
| `95 01` | Report Count = 1 |
| `75 01` | Report Size = 1 |
| `15 00` | Logical Min = 0 |
| `25 01` | Logical Max = 1 |
| `81 02` | Input = Data, Var, Abs |
| `05 01` | Usage Page = Generic Desktop |
| `09 37` | Usage = Dial |
| `95 01` | Report Count = 1 |
| `75 0F` | Report Size = 15 |
| `55 0F` | Unit Exponent = -1 |
| `65 14` | Unit = Degrees |
| `36 F0 F1` | Physical Min = -3600 |
| `46 10 0E` | Physical Max = 3600 |
| `16 F0 F1` | Logical Min = -3600 |
| `26 10 0E` | Logical Max = 3600 |
| `81 06` | Input = Data, Var, Rel |
| `C0` | End Physical Collection |
| `C0` | End Application Collection |

---

## 3. 为什么 Button + Dial 合成 16 bit

Descriptor 中先定义：

```text
Button 1 bit
Dial 15 bit
```

两者连续，因此 input report payload 是 16 bit：

```text
bit0      Button
bit1-15   Dial
```

这刚好是 2 字节。

---

## 4. bit packing 规则

### 4.1 payload 位图

```text
LSB first:

byte0 bit0 = button
byte0 bit1 = dial bit0
byte0 bit2 = dial bit1
...
byte1 bit7 = dial bit14
```

### 4.2 构造公式

```cpp
payload = ((delta & 0x7FFF) << 1) | (button ? 1 : 0)
```

### 4.3 小端发送

BLE notify value：

```cpp
report[0] = payload & 0xFF;
report[1] = payload >> 8;
```

---

## 5. 15-bit signed delta 说明

Dial 是 15 bit signed two's complement。

| delta | 15-bit 值 | 左移后 payload | bytes |
|---|---|---|---|
| 0 | `0x0000` | `0x0000` | `00 00` |
| +1 | `0x0001` | `0x0002` | `02 00` |
| -1 | `0x7FFF` | `0xFFFE` | `FE FF` |
| +10 | `0x000A` | `0x0014` | `14 00` |
| -10 | `0x7FF6` | `0xFFEC` | `EC FF` |

加上 button：

| button | delta | payload | bytes |
|---|---|---|---|
| 1 | 0 | `0x0001` | `01 00` |
| 1 | +1 | `0x0003` | `03 00` |
| 1 | -1 | `0xFFFF` | `FF FF` |
| 1 | +10 | `0x0015` | `15 00` |
| 1 | -10 | `0xFFED` | `ED FF` |

---

## 6. 测试用例

必须写入单元测试：

```text
buildRadialPayload(false, 0)  -> 00 00
buildRadialPayload(true, 0)   -> 01 00
buildRadialPayload(false, 1)  -> 02 00
buildRadialPayload(false, -1) -> FE FF
buildRadialPayload(true, 1)   -> 03 00
buildRadialPayload(true, -1)  -> FF FF
buildRadialPayload(false, 10) -> 14 00
buildRadialPayload(false,-10) -> EC FF
```

---

## 7. BLE HOGP value 不包含 Report ID

Radial report characteristic 的 ReportRef：

```text
01 01
```

已经说明：

```text
Report ID = 1
Report Type = Input
```

因此 notify value：

```text
02 00
```

不要发送：

```text
01 02 00
```

如果发成 3 字节，Windows 很可能把第一个 `01` 当成 Button，而后面的 bit 全部错位。

---

## 8. 与 Consumer Control 的区别

Consumer Control Media Dial：

```text
Report ID 2
ReportRef 02 01
1-byte payload
bit0 volume_up
bit1 volume_down
bit2 play_pause
bit3 mute
```

Radial Controller：

```text
Report ID 1
ReportRef 01 01
2-byte payload
bit0 button
bit1-15 dial relative
```

两者不要混用。

---

## 9. 日志建议

每次发送打印：

```text
>BLE radial report len=2 data=02 00 button=0 delta=1 hid=sent
```

不要只打印：

```text
hid=sent
```

否则无法判断字节是否正确。
