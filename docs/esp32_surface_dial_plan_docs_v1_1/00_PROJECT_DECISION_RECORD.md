# 00 项目阶段结论与决策记录

版本：v1.1

## 1. 项目目标

最终目标不是普通音量旋钮，而是：

> 使用 ESP32-S3 + 旋钮编码器模拟 Windows Surface Dial / Radial Controller 设备。

目标交互语义：

| 动作 | Surface Dial 语义 |
|---|---|
| 按住 | 打开 Windows RadialController 菜单 |
| 旋转 | 菜单内切换项目，或对当前工具/应用执行动作 |
| 点击 | 选择菜单项或触发应用命令 |
| 菜单关闭时旋转 | 将旋转事件交给当前 app / 当前 radial tool |

因此正式目标不应该长期停留在 Consumer Control 音量键。

---

## 2. 已验证成果

### 2.1 BLE HOGP 基础链路已被验证

前期日志已证明：

- BLE 初始化成功；
- Windows 能连接；
- HID over GATT 路径能跑；
- 编码器事件能进入 HID backend；
- 固件能打印 `hid=sent`；
- Windows 能消费 Consumer Control 媒体键。

这些结果说明项目已经越过了最初的“Windows 只加载 BthLEEnum / GenericDevice，不进入 HID 消费链路”的阶段。

---

## 3. Consumer Control 分支的意义

Consumer Control 分支不是最终产品，但它非常重要。

它证明：

| 能力 | 状态 |
|---|---|
| BLE 配对 / bonding | 已验证 |
| GATT HID service 基础枚举 | 已验证 |
| Input Report characteristic notify | 已验证 |
| Windows 对 BLE HID input report 的消费 | 已验证 |
| ESP32 编码器事件到 HID backend | 已验证 |
| Windows 对短按媒体键响应 | 已验证 |

因此应冻结一个稳定 Consumer Control 状态作为诊断基线。

建议 tag：

```bash
git tag ble-hid-no-force-encrypt-working
```

建议分支：

```bash
git branch test/ble-consumer-volume-no-force-encrypt-working
```

---

## 4. v1.1 最新关键决策：默认禁用强制加密级别

### 4.1 现象

此前 B+C Consumer Control 分支出现：

```text
connected 很多
disconnected 很多
hid_sent = 0
hid_skip > 0
BT_APPL: bta_dm_set_encryption, not find peer_bdaddr
BT_BTM: Device not found
```

初步推测为 Windows / ESP32 bond 或 encryption 状态不一致。

### 4.2 实验修复

实验分支中移除了：

```cpp
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
```

但保留：

```cpp
BLESecurity* bleSecurity = new BLESecurity();
bleSecurity->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
bleSecurity->setCapability(ESP_IO_CAP_NONE);
bleSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
bleSecurity->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
bleSecurity->setKeySize(16);
```

启动日志显示：

```text
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
```

### 4.3 实测结果

```text
connected     2
disconnected  0
hid_sent      86
hid_skip      0
```

旋转、短按、长按均出现稳定 `hid=sent`。

### 4.4 结论

强制调用：

```cpp
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
```

会在当前 Windows / ESP32-S3 BLE HID 场景下引发连接和 encryption 状态不稳定。

因此后续主线默认策略改为：

```text
保留 SC_BOND
保留 IO_NONE
保留 key mask
保留 CCCD / ReportRef 权限补丁
默认禁用 BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)
```

推荐代码形式：

```cpp
#ifndef BLE_FORCE_ENCRYPTION_LEVEL
#define BLE_FORCE_ENCRYPTION_LEVEL 0
#endif

#if BLE_FORCE_ENCRYPTION_LEVEL
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
#endif
```

---

## 5. 对 B+C 分支判断的修正

旧判断：

```text
B+C 分支本身不稳定，不适合作为起点。
```

v1.1 修正为：

```text
B+C 映射本身没有被证明有问题；
前一轮断连主要由强制 setEncryptionLevel 引发；
修复 no-force-encryption 后，B+C / Media Dial 可作为稳定 Consumer Control 诊断基线。
```

但必须强调：

```text
B+C 仍然是 Consumer Control / Media Dial，不是 Surface Dial / Radial Controller。
```

日志中仍然是：

```text
media report id: 2
report ref: 02 01
report map size: 33
1-byte media report
```

正式 Surface Dial 分支必须切换到：

```text
RADIAL_REPORT_ID = 1
ReportRef = 01 01
System Multi-Axis Controller
Button + Dial
2-byte radial payload
```

---

## 6. 正式主线决策

正式主线不继续堆 Consumer Control。

正式主线是：

```text
feature/ble-radial-controller-mvp
```

目标是最小 Windows Radial Controller：

- Top-level collection：Generic Desktop / System Multi-Axis Controller；
- Physical collection：Digitizers / Puck；
- Mandatory inputs：Button + Dial；
- BLE Report ID：1；
- BLE notify value：2 字节 payload，不带 Report ID；
- Windows 端用 RadialController API 验证事件，而不是用系统音量变化作为成功标准。

---

## 7. 重要决策表

| 议题 | 决策 |
|---|---|
| 继续 Consumer Control？ | 否，只保留为诊断基线 |
| 正式设备类型 | Windows Radial Controller / Surface Dial 类设备 |
| BLE 初始化基线 | SC_BOND + IO_NONE + no forced encryption |
| 是否默认调用 `setEncryptionLevel` | 否 |
| 验证标准 | Windows RadialController API 能收到 Button / Rotation 事件 |
| 是否继续用音量变化验证 | 只用于诊断，不作为最终标准 |
| BLE notify 是否包含 Report ID | 不包含 |
| Radial Controller 初版是否包含 haptic | 不包含，MVP 成功后再做 |
| 是否先做 on-screen puck | 不做，后期增强 |
| 当前 B+C no-force-encrypt 状态 | 可作为诊断基线，不作为最终产品 |

---

## 8. 成功定义

MVP 成功不是“音量变化”，而是：

```text
Windows 把 ESP32 识别并消费为 RadialController；
Windows probe app 能收到 RotationChanged；
按钮按下/释放能触发 RadialController 相关事件；
长按能进入 Radial 菜单行为或至少被 Windows/app 识别为 button hold。
```
