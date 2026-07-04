# 03 BLE HOGP Report ID、Report Reference、Windows 缓存与加密规则

版本：v1.1

## 1. 为什么这份文档重要

ESP32 BLE HID 项目最容易失败在三个地方：

1. USB HID 和 BLE HOGP 对 Report ID 的处理差异；
2. Windows 对 BLE GATT/HID 数据库的缓存；
3. ESP32 主动强制 encryption level 与 Windows bonding 状态冲突。

如果这里处理错，就会出现：

- 固件打印 `hid=sent`，Windows 没反应；
- Windows 连接后马上断开；
- Windows 继续使用旧 Report Map；
- 改了 descriptor 但表现不变；
- `BT_BTM: Device not found`；
- `bta_dm_set_encryption` 错误。

---

## 2. USB HID 和 BLE HOGP 的关键差异

### 2.1 USB HID

USB HID 多 report 时，report payload 通常包含 Report ID：

```text
[Report ID][payload...]
```

例如：

```text
01 FE FF
```

### 2.2 BLE HOGP

BLE HOGP 中，`inputReport(REPORT_ID)` 会创建一个 Report characteristic。该 characteristic 旁边的 Report Reference descriptor `0x2908` 已经声明了：

```text
Report ID
Report Type
```

因此 characteristic notify value 应只放 payload：

```text
[payload...]
```

不要再塞 Report ID。

---

## 3. BLE encryption 策略

### 3.1 保留 bonding

继续使用：

```text
SC_BOND + IO_NONE
```

保留 key mask：

```cpp
bleSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
bleSecurity->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
```

### 3.2 默认不强制 `setEncryptionLevel`

不要默认调用：

```cpp
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
```

最新实测中，关闭该调用后：

```text
disconnected=0
hid_sent=86
hid_skip=0
```

因此主线策略：

```cpp
#ifndef BLE_FORCE_ENCRYPTION_LEVEL
#define BLE_FORCE_ENCRYPTION_LEVEL 0
#endif

#if BLE_FORCE_ENCRYPTION_LEVEL
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
#endif
```

日志必须打印：

```text
[BLE-HID] force encryption level: disabled
```

### 3.3 判断是否误启用

如果日志出现：

```text
bta_dm_set_encryption, not find peer_bdaddr
BT_BTM: Device not found
connected/disconnected 反复刷屏
```

第一步检查：

```text
BLE_FORCE_ENCRYPTION_LEVEL 是否被设成 1
```

---

## 4. Radial MVP 的正确 BLE value

### 4.1 Report Reference

```text
01 01
```

含义：

| Byte | 含义 |
|---|---|
| `01` | Report ID 1 |
| `01` | Input Report |

### 4.2 Notify value

```text
2 bytes only
```

示例：

| 事件 | notify value |
|---|---|
| idle | `00 00` |
| button down | `01 00` |
| button up | `00 00` |
| dial +1 | `02 00` |
| dial -1 | `FE FF` |

---

## 5. 什么时候需要改 BLE identity

每当修改这些内容时，应临时改变 BLE identity：

- Report Map；
- Report ID；
- Report Reference；
- input report characteristic 数量；
- HID service layout；
- Device Information Service；
- security / bonding 模式；
- encryption 策略；
- 从 Media Dial 切到 Radial Controller。

建议同时改：

```text
设备名
稳定 random static address 扰动值
```

例如：

```cpp
#define BLE_IDENTITY_SUFFIX 0x31
addr[5] ^= BLE_IDENTITY_SUFFIX;
```

设备名：

```cpp
"ESP32-S3 Radial MVP"
```

下一次重大 descriptor 变更：

```cpp
#define BLE_IDENTITY_SUFFIX 0x32
"ESP32-S3 Radial MVP2"
```

---

## 6. Windows 缓存策略

### 6.1 不推荐每次手动清 Windows 缓存

用户目标是开发固件。为了减少 Windows 端手动操作，开发期可以通过改 BLE identity 避免旧缓存。

### 6.2 推荐命名策略

| 分支 / 实验 | 设备名 | address 扰动 |
|---|---|---|
| Consumer no-force-encrypt working | `ESP32-S3 Media Dial NE` | `0x24` |
| Radial MVP | `ESP32-S3 Radial MVP` | `0x31` |
| Radial MVP report fix | `ESP32-S3 Radial MVP2` | `0x32` |
| Haptic experiment | `ESP32-S3 Radial Haptic` | `0x41` |

---

## 7. 断连问题排查

### 7.1 日志特征

如果看到：

```text
connected
disconnected
connected
disconnected
BT_BTM: Device not found
bta_dm_set_encryption, not find peer_bdaddr
```

说明优先怀疑：

1. 是否误启用了 `BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)`；
2. Windows 使用旧缓存；
3. 当前 Report Map 与 bonded 数据不一致；
4. Report Reference 和实际 characteristic 不一致；
5. 设备名变了但地址没变；
6. 连接回调中立即重启 advertising；
7. 固件同时存在多个历史 input report。

---

## 8. 初始化阶段必须打印的内容

每次启动必须打印完整地址和报告参数：

```text
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
[BLE-HID] address: XX:XX:XX:XX:XX:XX
[BLE-HID] radial report id: 1
[BLE-HID] radial report ref: 01 01
[BLE-HID] report map size: N
```

不要只打印：

```text
E8:84:85:B5:
```

因为无法确认最后两个字节是否真的变化。

---

## 9. 固件权限规则

前期经验表明：

- Input Report characteristic 本体可以要求加密；
- CCCD `0x2902` 建议开放读写；
- Report Reference `0x2908` 建议开放读；
- 这样可以降低 Windows 枚举早期失败概率。

继续保留：

```cpp
fixHogpInputReportPermissions(inputReport);
```

不要在 Radial MVP 中重新改 security。

---

## 10. 禁止混入旧报告

Radial MVP 分支不应该出现：

```text
MEDIA_REPORT_ID
Consumer Control 0x0C
Volume Increment 0xE9
Volume Decrement 0xEA
Mute 0xE2
Play/Pause 0xCD
Mouse Wheel
Joystick
```

如果为了诊断需要 Consumer Control，应切回独立诊断分支，不要混在 Radial MVP 分支。
