# BLE HID Driver Error — Complete Debugging Log

> 2026-07-04 | ESP32-S3 BLE HID Dial | Windows 10 19041 | Arduino ESP32 Core 2.0.17

---

## Final Symptom

Windows BLE 配对成功（Just Works 加密通过），但设备管理器始终加载 **BthLEEnum** 驱动
（匹配 `BTHLE\GenericDevice`，类 GUID `{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}`），
不加载 HID-over-GATT 驱动。设备无法发送 HID 报告给 Windows。

---

## Problem #1: BLE 随机地址每次重启变化

**文件**: `esp32s3_touch_dial.ino` line ~234 `fillBleDialRandomAddress()`

**问题**: 函数使用 `esp_random()`（硬件真随机数）生成 BLE 地址。每次 reboot 地址完全不同，
Windows 配对绑定到旧地址，重启后设备变成"陌生人"。

**改动**: 改为从 `esp_read_mac(baseMac, ESP_MAC_BT)` 基 MAC 派生，`addr[0] | 0xC0` 满足
BLE random static address 格式要求（高两位 = 11）。

**文件变更**:
```diff
-  uint32_t r0 = esp_random();
-  uint32_t r1 = esp_random();
-  addr[0] = static_cast<uint8_t>((r0 & 0x3F) | 0xC0);
+  uint8_t baseMac[6];
+  esp_read_mac(baseMac, ESP_MAC_BT);
+  addr[0] = baseMac[0] | 0xC0;
```

---

## Problem #2: Input Report 特征要求加密访问

**文件**: ESP32 BLE 库 `BLEHIDDevice.cpp` line 118-120（库源码，非项目文件）

**问题**: `BLEHIDDevice::inputReport()` 对 input report 特征 (0x2A4D)、CCCD (0x2902)、
Report Reference (0x2908) 设置了 `ESP_GATT_PERM_READ_ENCRYPTED | ESP_GATT_PERM_WRITE_ENCRYPTED`。
Windows 连接后尝试启用 CCCD 通知 → 触发加密配对 → ESP32 无 IO 能力配置 → 配对失败 →
Windows 显示"请尝试重新连接设备"并断开。

**改动** (已回退): 在 `startServices()` 前调用 `setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE)`
覆盖加密权限。后来与 Just Works 安全方案合并后回退此改动，恢复库默认加密权限。

**文件变更** (`esp32s3_touch_dial.ino`):
```diff
   bleDialInputReport = bleDialHid->inputReport(DIAL_REPORT_ID);
+  bleDialInputReport->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
+  BLEDescriptor* cccd = bleDialInputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
+  if (cccd) cccd->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
+  BLEDescriptor* rptRef = bleDialInputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2908));
+  if (rptRef) rptRef->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
```
(后续与 Problem #3 合并后移除此段，恢复库默认)

---

## Problem #3: 缺少 BLESecurity 配置导致配对失败

**文件**: `esp32s3_touch_dial.ino` `beginDialBackend()` 函数

**问题**: ESP-IDF Bluedroid 默认认证模式为 `ESP_LE_AUTH_REQ_SC_MITM_BOND`（要求 MITM 保护），
默认 IO 能力为 `ESP_IO_CAP_NONE`（无输入输出）。MITM 要求 + 无 IO = 配对永远失败。
即使移除加密权限，Windows 仍可能主动要求加密链路。

**改动**: 在 `BLEDevice::init()` 之后创建 `BLESecurity` 对象，设置 Just Works 模式：
无需 bonding、无 IO 能力、16 字节密钥、启用连接级加密。

**文件变更** (`esp32s3_touch_dial.ino` line ~908):
```diff
   BLEDevice::init(USB_PRODUCT_NAME);
+  {
+    BLESecurity* bleSecurity = new BLESecurity();
+    bleSecurity->setAuthenticationMode(ESP_LE_AUTH_NO_BOND);
+    bleSecurity->setCapability(ESP_IO_CAP_NONE);
+    bleSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
+    bleSecurity->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
+    bleSecurity->setKeySize(16);
+  }
+  BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
```
新增 `#include "BLESecurity.h"` (line 28).

---

## Problem #4: Report ID 10 可能干扰 Windows

**文件**: `esp32s3_touch_dial.ino` line 105

**问题**: `DIAL_REPORT_ID = 10` 作为显式报告 ID 写入描述符 (`0x85, 10`)。某些 Windows HID
解析器对非零 Report ID 敏感，可能导致驱动加载失败。

**改动**: `DIAL_REPORT_ID` 改为 0，描述符中移除 `0x85` 项。报告格式不变（仍为原始数据字节）。

**文件变更** (`esp32s3_touch_dial.ino` line 105):
```diff
-constexpr uint8_t DIAL_REPORT_ID = 10;
+constexpr uint8_t DIAL_REPORT_ID = 0;
```
描述符中移除:
```diff
-  0x85, DIAL_REPORT_ID,
```

---

## Problem #5: 广告数据中 HID 服务 UUID 使用了 128-bit 格式导致溢出

**文件**: `esp32s3_touch_dial.ino` `beginDialBackend()`

**问题**: 第一次尝试同时广播 HID (0x1812) 和 Battery (0x180F) 两个服务时，
使用了 `bleDialAdvertising->addServiceUUID()`。但 ESP32 BLE 库的 `addServiceUUID()` 会将
所有 UUID 转为 128-bit 格式（`to128()`），每个 UUID 占 16 字节。2 个 UUID = 32 字节 +
AD 头部 = 34 字节，超出 BLE 广告数据 31 字节限制。广告数据被截断，Windows 无法看到完整 UUID。

**改动**: 改用手动构造 16-bit AD 元素 `{0x05, 0x03, 0x12, 0x18, 0x0F, 0x18}`（AD type 0x03 =
Complete List of 16-bit Service UUIDs），总共 6 字节。

**文件变更** (`esp32s3_touch_dial.ino`):
```diff
-  bleDialAdvertising->addServiceUUID(bleDialHid->hidService()->getUUID());
-  bleDialAdvertising->addServiceUUID(BLEUUID((uint16_t)0x180F));
+  uint8_t svcAD[] = {0x05, 0x03, 0x12, 0x18, 0x0F, 0x18};
+  bleAdvData.addData(std::string(reinterpret_cast<char*>(svcAD), sizeof(svcAD)));
```

---

## Problem #6: Windows 不认 HID 设备 — 始终加载 BthLEEnum（未解决）

**现象**: 解决 Problem 1-5 后，配对成功、BLE 链路加密通过、广告含 HID+Battery 服务 UUID、
描述符为最简 Generic Desktop X (1 byte)。但 Windows 设备管理器仍显示 **BthLEEnum** 驱动，
匹配 `BTHLE\GenericDevice`。

**尝试过的描述符变体**（均无效，证明不是描述符内容问题）:
1. System Multi-Axis Controller (0x0E) + Dial (0x37) — 原始 Baseline
2. Multi-axis Controller (0x08) + Dial (0x37) — VariantA
3. Mouse (0x02) + Wheel (0x38) + Button — 鼠标方案
4. Generic Desktop X (0x30) 单轴 — 最简方案（仅 19 字节）

**尝试过的外观变体**（均无效）:
1. GENERIC_HID (0x03C0)
2. HID_JOYSTICK (0x03C3)
3. HID_MOUSE (0x03C2)

**尝试过的地址模式**（均无效）:
1. 真随机地址 (`esp_random()`)
2. 基 MAC 派生随机静态地址
3. 默认公共地址（不调用 `setDeviceAddress()`）

**尝试过的广告数据格式**（均无效）:
1. 自定义 AD + `setCompleteServices`（仅 HID UUID）
2. 自定义 AD + `addServiceUUID`（128-bit 溢出）
3. 自定义 AD + 手动 16-bit 双 UUID
4. Name 在 scan response / 在 primary AD

**当前假设**: 问题在 GATT 层。Windows 连接后读取 HID Service 特征时，某个必须特征
（Report Map 0x2A4B, HID Info 0x2A4A, Protocol Mode 0x2A4E 等）返回值异常或读取失败，
导致 Windows 无法完成 HID 枚举，回退到 BthLEEnum。

**待验证方向**:
1. 用 BLE sniffer/nRF Connect 抓取 GATT 交互，看 Windows 到底读了哪些特征、返回值是什么
2. 手动创建 HID GATT 服务，绕过 `BLEHIDDevice` 库
3. 尝试不同 ESP32 Arduino core 版本
4. 尝试 `ESP_LE_AUTH_REQ_SC_BOND`（Secure Connections + Bonding）替代 NO_BOND
5. 检查 Battery Service characteristic 的描述符 0x2904 格式是否正确

---

## Problem #7: 描述符内容正确但可能格式不兼容

**文件**: `esp32s3_touch_dial.ino` line ~125

**问题**: 描述符本身语法正确（可通过 HID 解析器验证），但 ESP32 BLE 库在 GATT 注册时可能有
格式问题。`BLECharacteristic::executeCreate()` 创建 GATT 属性时传入 `nullptr` 作为初始值，
实际值由读回调动态返回。如果 Bluedroid 栈在 Windows 读取前未正确注册读回调，返回值可能为空。

**当前状态**: 未验证。需要 BLE sniffer 或 GATT 客户端工具确认。

---

## File Inventory

| 文件 | 改动摘要 |
|------|---------|
| `esp32s3_touch_dial.ino` | 添加 BLESecurity 配置、BLE_DIAL_APPEARANCE 常量、BleDialDescriptorProfile 枚举、稳定地址生成、加密级别设置、双服务 16-bit AD、多次描述符切换 |
| `tests/test_ble_backend_init_order.py` | 多次适配广告数据格式和地址方案的测试更新 |
| `tests/test_hid_capture_analysis.py` | BLE 发送结果可见性增强 |
| `tools/analyze_hid_captures.py` | 分析工具增强 |

## Git Commits

```
afa7b1c docs: add BLE dial backend planning and validation documents
7fc770b test: add BLE backend init order test and capture analysis enhancements
8620e6b refactor: extract BLE HID identity constants, appearance tuning round 1
(多位未推的改动在 working tree 中，继续迭代)
```
