# 03 BLE HOGP Report ID、Report Reference、Windows 缓存规则

## 1. 为什么这份文档重要

ESP32 BLE HID 项目最容易失败在两个地方：

1. USB HID 和 BLE HOGP 对 Report ID 的处理差异；
2. Windows 对 BLE GATT/HID 数据库的缓存。

如果这里处理错，就会出现：固件打印 `hid=sent`，Windows 没反应；Windows 连接后马上断开；改了 descriptor 但表现不变。

## 2. USB HID 和 BLE HOGP 的关键差异

### 2.1 USB HID

USB HID 多 report 时，report payload 通常包含 Report ID：

```text
[Report ID][payload...]
```

### 2.2 BLE HOGP

BLE HOGP 中，`inputReport(REPORT_ID)` 会创建一个 Report characteristic。该 characteristic 旁边的 Report Reference descriptor `0x2908` 已经声明了 Report ID 和 Report Type。

因此 characteristic notify value 应只放 payload，不要再塞 Report ID。

## 3. Radial MVP 的正确 BLE value

### 3.1 Report Reference

```text
01 01
```

| Byte | 含义 |
|---|---|
| `01` | Report ID 1 |
| `01` | Input Report |

### 3.2 Notify value

```text
2 bytes only
```

| 事件 | notify value |
|---|---|
| idle | `00 00` |
| button down | `01 00` |
| button up | `00 00` |
| dial +1 | `02 00` |
| dial -1 | `FE FF` |

## 4. 什么时候需要改 BLE identity

每当修改这些内容时，应临时改变 BLE identity：

- Report Map；
- Report ID；
- Report Reference；
- input report characteristic 数量；
- HID service layout；
- Device Information Service；
- security / bonding 模式。

建议同时改设备名和稳定 random static address 扰动值。

```cpp
#define BLE_IDENTITY_SUFFIX 0x31
addr[5] ^= BLE_IDENTITY_SUFFIX;
```

设备名：

```cpp
"ESP32-S3 Radial MVP"
```

## 5. Windows 缓存策略

开发期可以通过改 BLE identity 避免旧缓存。

| 分支 / 实验 | 设备名 | address 扰动 |
|---|---|---|
| Consumer working | `ESP32-S3 Media Dial` | `0x22` |
| Radial MVP | `ESP32-S3 Radial MVP` | `0x31` |
| Radial MVP report fix | `ESP32-S3 Radial MVP2` | `0x32` |
| Haptic experiment | `ESP32-S3 Radial Haptic` | `0x41` |

## 6. 断连问题排查

如果看到：

```text
connected
disconnected
connected
disconnected
BT_BTM: Device not found
bta_dm_set_encryption, not find peer_bdaddr
```

优先怀疑：Windows 使用旧缓存；当前 Report Map 与 bonded 数据不一致；Report Reference 和实际 characteristic 不一致；设备名变了但地址没变；过早或重复调用 encryption；固件同时存在多个历史 input report。

## 7. 初始化阶段必须打印的内容

```text
[BLE-HID] address: XX:XX:XX:XX:XX:XX
[BLE-HID] radial report id: 1
[BLE-HID] radial report ref: 01 01
[BLE-HID] report map size: N
```

不要只打印 `E8:84:85:B5:`，因为无法确认最后两个字节是否真的变化。

## 8. 固件权限规则

继续保留：

```cpp
fixHogpInputReportPermissions(inputReport);
```

不要在 Radial MVP 中重新改 security。

## 9. 禁止混入旧报告

Radial MVP 分支不应该出现：`MEDIA_REPORT_ID`、Consumer Control `0x0C`、Volume Increment、Volume Decrement、Mute、Play/Pause、Mouse Wheel、Joystick。
