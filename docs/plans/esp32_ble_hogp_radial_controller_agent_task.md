# ESP32-S3 BLE HID Surface Dial / Radial Controller 修复任务书

> 目标读者：代码 Agent / 本地开发 Agent / 自动化修复 Agent  
> 范围：仅包含 ESP32 项目代码、固件、测试、验证与提交要求。  
> 明确排除：Windows 端手动操作、Windows 设备管理器操作、Windows 蓝牙缓存清理、Windows 注册表操作。

---

## 0. 背景

项目目标是使用 ESP32-S3 模拟 Microsoft Surface Dial / Windows Radial Controller。

当前现象：

- Windows BLE 配对能够成功；
- Just Works 加密可以通过；
- 广告中已经包含 HID Service / Battery Service；
- 但 Windows 设备管理器始终只加载 `BthLEEnum / GenericDevice`；
- 没有继续枚举出 HID-over-GATT / Radial Controller 子设备；
- HID 报告无法被 Windows 作为输入设备接收。

现有调试日志已经证明以下方向多次尝试无效：

- 多种 HID Report Descriptor 变体；
- 多种 Appearance 值；
- 多种 BLE 地址模式；
- 多种广告数据格式；
- Report ID 0 / 非 0 的切换。

因此，本任务不继续随机更换 HID 描述符，而是从 HOGP 枚举链路修复：

1. BLE security / bonding；
2. HID-over-GATT 必要服务；
3. Report Map / Report Reference / CCCD 权限；
4. Surface Dial / Radial Controller 最小合规描述符；
5. 固件侧自测与项目测试。

---

## 1. 总体目标

让 ESP32-S3 作为 BLE HID over GATT Peripheral，被主机识别为可枚举的 HID / Radial Controller 设备。

本阶段目标不是完整复刻 Surface Dial 的全部体验，而是先达成：

- GATT 中存在完整 HID Service；
- Report Map 可以被客户端稳定读取；
- Input Report 具备正确 Report Reference；
- CCCD 可以被客户端写入；
- 设备使用 bond-capable Just Works；
- 固件能发送符合 Radial Controller 最小输入格式的 report。

---

## 2. 明确禁止事项

Agent 不要做以下事情：

- 不要继续随机切换 Mouse / Joystick / X Axis / Multi-Axis 等描述符变体；
- 不要把 Windows 端清缓存步骤写入本项目代码任务；
- 不要修改 Windows 注册表；
- 不要依赖 Windows 设备管理器作为唯一验证标准；
- 不要将 `NO_BOND` 作为最终 HID 主路径；
- 不要继续使用真随机 BLE 地址；
- 不要让广告数据超过 31 字节；
- 不要把多个 16-bit UUID 通过 `addServiceUUID()` 转成 128-bit 后塞进 primary advertising data；
- 不要把最终 Surface Dial 路线建立在 Report ID 0 上。

---

## 3. 需要修改的主要文件

优先搜索并修改：

- `esp32s3_touch_dial.ino`

可能需要同步更新：

- `tests/test_ble_backend_init_order.py`
- `tests/test_hid_capture_analysis.py`
- `tools/analyze_hid_captures.py`
- 项目 README / docs 中与 BLE HID 相关的固件说明

不要新增 Windows 操作说明文档。

---

## 4. 修改任务 A：BLE Security 改为 Bonding + Just Works

### 4.1 当前风险

当前代码曾使用：

```cpp
bleSecurity->setAuthenticationMode(ESP_LE_AUTH_NO_BOND);
```

这不适合作为 BLE HID 主路径。

BLE HID / HOGP 外设应当允许主机完成 pairing 并保存 bond。

### 4.2 目标改法

在 `BLEDevice::init(USB_PRODUCT_NAME);` 之后配置：

```cpp
#include "BLESecurity.h"
```

```cpp
BLEDevice::init(USB_PRODUCT_NAME);

{
  BLESecurity* bleSecurity = new BLESecurity();

  // HID 外设使用可 Bond 的 Just Works。
  // 设备无屏幕、无键盘，因此 IO capability 为 NONE。
  bleSecurity->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
  bleSecurity->setCapability(ESP_IO_CAP_NONE);

  bleSecurity->setInitEncryptionKey(
      ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK
  );
  bleSecurity->setRespEncryptionKey(
      ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK
  );

  bleSecurity->setKeySize(16);
}

BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
```

### 4.3 兼容降级

如果当前 Arduino ESP32 Core / 编译环境不支持 `ESP_LE_AUTH_REQ_SC_BOND`，尝试：

```cpp
bleSecurity->setAuthenticationMode(ESP_LE_AUTH_BOND);
```

但不要退回 `ESP_LE_AUTH_NO_BOND` 作为主路径。

### 4.4 验收标准

代码中不应再出现以下最终配置：

```cpp
ESP_LE_AUTH_NO_BOND
```

除非它只存在于注释、历史说明或测试样例中。

---

## 5. 修改任务 B：恢复稳定 BLE 地址生成

### 5.1 当前风险

曾经使用 `esp_random()` 生成 BLE 地址，导致每次重启地址不同。

BLE HID 设备不能每次重启变成新设备。

### 5.2 目标改法

保留或实现基于 BT base MAC 派生的 random static address：

```cpp
static void fillBleDialRandomAddress(uint8_t addr[6]) {
  uint8_t baseMac[6] = {0};

  esp_err_t err = esp_read_mac(baseMac, ESP_MAC_BT);
  if (err != ESP_OK) {
    esp_read_mac(baseMac, ESP_MAC_WIFI_STA);
  }

  memcpy(addr, baseMac, 6);

  // BLE random static address 要求最高两位为 11。
  addr[0] = static_cast<uint8_t>(addr[0] | 0xC0);
}
```

### 5.3 验收标准

不得使用如下逻辑作为最终地址来源：

```cpp
esp_random()
```

地址应在同一块板子上跨 reboot 保持稳定。

---

## 6. 修改任务 C：广告数据改为短 16-bit Service UUID 列表

### 6.1 当前风险

`BLEAdvertising::addServiceUUID()` 在某些 Arduino ESP32 BLE 库实现中会把 UUID 转成 128-bit，导致多个服务 UUID 超出 31 字节 primary advertising data 限制。

### 6.2 目标广告内容

Primary advertising data 中应至少包含：

- Flags；
- Appearance；
- Complete List of 16-bit Service UUIDs；
- 名称可以放到 scan response，避免 primary adv 超长。

服务 UUID 使用：

- `0x1812` Human Interface Device；
- `0x180F` Battery Service；
- `0x180A` Device Information Service。

### 6.3 目标代码片段

```cpp
BLEAdvertisementData bleAdvData;
BLEAdvertisementData bleScanData;

bleAdvData.setFlags(ESP_BLE_ADV_FLAG_GEN_DISC | ESP_BLE_ADV_FLAG_BREDR_NOT_SPT);

// Appearance: Generic HID = 0x03C0
// AD type 0x19, little-endian value C0 03
{
  uint8_t appearanceAD[] = {0x03, 0x19, 0xC0, 0x03};
  bleAdvData.addData(
      std::string(reinterpret_cast<char*>(appearanceAD), sizeof(appearanceAD))
  );
}

// Complete List of 16-bit Service UUIDs:
// 0x1812 HID, 0x180F Battery, 0x180A Device Information
{
  uint8_t svcAD[] = {
    0x07, 0x03,
    0x12, 0x18,
    0x0F, 0x18,
    0x0A, 0x18
  };
  bleAdvData.addData(
      std::string(reinterpret_cast<char*>(svcAD), sizeof(svcAD))
  );
}

// 设备名放 scan response，减少 primary adv 压力。
bleScanData.setName(USB_PRODUCT_NAME);

bleDialAdvertising->setAdvertisementData(bleAdvData);
bleDialAdvertising->setScanResponseData(bleScanData);
```

### 6.4 验收标准

测试中应确认：

- primary advertising data 不超过 31 字节；
- 不通过 `addServiceUUID()` 添加 HID/Battery/DIS 三个服务；
- 16-bit Service UUID AD element 中包含 `12 18 0F 18 0A 18`。

---

## 7. 修改任务 D：使用最小 Radial Controller Report Descriptor

### 7.1 当前方向

恢复 Report ID：

```cpp
constexpr uint8_t DIAL_REPORT_ID = 1;
```

不要继续使用 Report ID 0 作为 Surface Dial 主路径。

### 7.2 最小描述符

将当前用于 Windows 验证的主描述符固定为：

```cpp
static const uint8_t radialControllerReportMap[] = {
  0x05, 0x01,        // Usage Page (Generic Desktop)
  0x09, 0x0E,        // Usage (System Multi-Axis Controller)
  0xA1, 0x01,        // Collection (Application)

  0x85, 0x01,        //   Report ID (1)

  0x05, 0x09,        //   Usage Page (Button)
  0x09, 0x01,        //   Usage (Button 1)
  0x95, 0x01,        //   Report Count (1)
  0x75, 0x01,        //   Report Size (1)
  0x15, 0x00,        //   Logical Min (0)
  0x25, 0x01,        //   Logical Max (1)
  0x81, 0x02,        //   Input (Data, Var, Abs)

  0x05, 0x01,        //   Usage Page (Generic Desktop)
  0x09, 0x37,        //   Usage (Dial)
  0x95, 0x01,        //   Report Count (1)
  0x75, 0x0F,        //   Report Size (15)
  0x55, 0x0F,        //   Unit Exponent (-1)
  0x65, 0x14,        //   Unit (Degrees, English Rotation)
  0x36, 0xF0, 0xF1,  //   Physical Min (-3600)
  0x46, 0x10, 0x0E,  //   Physical Max (3600)
  0x16, 0xF0, 0xF1,  //   Logical Min (-3600)
  0x26, 0x10, 0x0E,  //   Logical Max (3600)
  0x81, 0x06,        //   Input (Data, Var, Rel)

  0xC0               // End Collection
};
```

### 7.3 应用描述符

确保 HID Report Map 使用上述数组：

```cpp
bleDialHid->reportMap(
    const_cast<uint8_t*>(radialControllerReportMap),
    sizeof(radialControllerReportMap)
);
```

如项目内已存在 profile enum，例如：

```cpp
enum class BleDialDescriptorProfile
```

请保留枚举，但默认 profile 必须指向该最小 Radial Controller 描述符。

### 7.4 验收标准

测试应确认：

- 描述符包含 `05 01 09 0E`；
- 描述符包含 `85 01`；
- 描述符包含 Button `05 09 09 01`；
- 描述符包含 Dial `05 01 09 37`；
- 描述符以 `C0` 结束；
- 默认编译路径不使用 Mouse / X Axis 极简描述符。

---

## 8. 修改任务 E：修复 Input Report / CCCD / Report Reference 权限

### 8.1 当前风险

Arduino ESP32 `BLEHIDDevice::inputReport()` 会对 Input Report、CCCD、Report Reference 设置加密权限。

Windows / GATT 客户端在枚举早期需要稳定读取 Report Reference，并写入 CCCD 以启用 notify。

因此需要对 descriptor 权限进行补丁。

### 8.2 目标函数

新增：

```cpp
static void fixHogpInputReportPermissions(BLECharacteristic* inputReport) {
  if (!inputReport) return;

  // Report characteristic 本体可以继续要求加密。
  inputReport->setAccessPermissions(
      ESP_GATT_PERM_READ_ENCRYPTED | ESP_GATT_PERM_WRITE_ENCRYPTED
  );

  // Report Reference Descriptor: 0x2908
  // Windows 枚举 HID Report 时需要读取。
  BLEDescriptor* reportRef =
      inputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2908));
  if (reportRef) {
    reportRef->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
  }

  // Client Characteristic Configuration Descriptor: 0x2902
  // 主机需要写入以启用 notify。
  BLEDescriptor* cccd =
      inputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
  if (cccd) {
    cccd->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
  }
}
```

### 8.3 调用位置

在创建 input report 后立即调用：

```cpp
bleDialInputReport = bleDialHid->inputReport(DIAL_REPORT_ID);
fixHogpInputReportPermissions(bleDialInputReport);
```

调用必须发生在：

```cpp
bleDialHid->startServices();
```

之前。

### 8.4 验收标准

测试或日志应确认：

- Input Report Characteristic 存在；
- 0x2908 Report Reference Descriptor 存在；
- 0x2902 CCCD 存在；
- 修复函数在 `startServices()` 前执行；
- Report Reference value 应为 `{0x01, 0x01}`，即 Report ID 1 + Input Report。

---

## 9. 修改任务 F：补齐 Device Information Service

### 9.1 目标

HOGP 设备应有 Device Information Service，至少提供 PnP ID。

### 9.2 目标实现

如果当前 `BLEHIDDevice` 已经提供相关方法，优先使用库方法：

```cpp
bleDialHid->manufacturer()->setValue("A-BOT-GIT");
bleDialHid->pnp(0x02, 0x1234, 0x5678, 0x0100);
bleDialHid->hidInfo(0x00, 0x01);
```

说明：

- `0x02` 表示 Vendor ID Source 为 USB-IF；
- `0x1234 / 0x5678` 是临时开发 VID/PID，占位值；
- 后续正式项目应替换为合法 VID/PID 或项目约定 ID；
- `hidInfo(0x00, 0x01)` 代表 HID country code 0，flags 1。

如果库 API 名称不同，Agent 应搜索 `BLEHIDDevice` 类定义确认实际方法签名。

### 9.3 验收标准

GATT 中应存在：

```text
180A Device Information
  2A50 PnP ID
```

如果库自动把 DIS 合并到 HID 初始化过程中，也要在测试或日志中确认它实际存在。

---

## 10. 修改任务 G：发送符合 Radial Controller 的输入报告

### 10.1 报告格式

当前最小描述符定义：

- Report ID：1；
- Button：1 bit；
- Dial：15 bit，relative，单位为 0.1 degree。

发送 report 长度应为 3 字节：

```text
byte0: Report ID = 0x01
byte1: payload low byte
byte2: payload high byte
```

payload bit 布局：

```text
bit0: Button 1 pressed
bit1..bit15: signed 15-bit dial delta
```

### 10.2 目标发送函数

```cpp
static void sendDialReport(int16_t deltaTenthsDeg, bool pressed) {
  if (!bleDialConnected || !bleDialInputReport) return;

  if (deltaTenthsDeg > 3600) deltaTenthsDeg = 3600;
  if (deltaTenthsDeg < -3600) deltaTenthsDeg = -3600;

  uint16_t dial15 = static_cast<uint16_t>(deltaTenthsDeg) & 0x7FFF;
  uint16_t payload = static_cast<uint16_t>((dial15 << 1) | (pressed ? 1 : 0));

  uint8_t report[3] = {
    DIAL_REPORT_ID,
    static_cast<uint8_t>(payload & 0xFF),
    static_cast<uint8_t>((payload >> 8) & 0xFF)
  };

  bleDialInputReport->setValue(report, sizeof(report));
  bleDialInputReport->notify();
}
```

### 10.3 验收标准

测试应确认：

- `sizeof(report) == 3`；
- `report[0] == 0x01`；
- 正向旋转、反向旋转、按压三类输入都调用该函数；
- 不再发送旧的 1 字节原始报告作为主路径。

---

## 11. 修改任务 H：添加固件侧调试日志

### 11.1 目标

增加串口日志，方便确认 HOGP 初始化顺序。

### 11.2 建议日志点

至少打印：

```text
[BLE-HID] init start
[BLE-HID] security: SC_BOND + IO_NONE + ENC
[BLE-HID] address: <addr>
[BLE-HID] report id: 1
[BLE-HID] report map size: <n>
[BLE-HID] adv services: 1812,180F,180A
[BLE-HID] input report created
[BLE-HID] descriptor permissions patched: 2908=<yes/no>, 2902=<yes/no>
[BLE-HID] services started
[BLE-HID] advertising started
[BLE-HID] connected
[BLE-HID] disconnected
[BLE-HID] notify report: id=1 delta=<n> pressed=<0/1>
```

### 11.3 验收标准

编译运行后，串口日志能明确看出：

- security 在 services start 前完成；
- input report 在 services start 前创建；
- descriptor patch 在 services start 前完成；
- advertising 在 services start 后启动。

---

## 12. 修改任务 I：项目测试要求

### 12.1 更新 `tests/test_ble_backend_init_order.py`

添加或更新测试，覆盖：

1. `BLEDevice::init()` 之后配置 `BLESecurity`；
2. 不使用 `ESP_LE_AUTH_NO_BOND` 作为最终路径；
3. 使用 `ESP_LE_AUTH_REQ_SC_BOND` 或兼容 bond 配置；
4. `fixHogpInputReportPermissions()` 在 `startServices()` 前调用；
5. primary advertising data 使用手工 16-bit UUID AD element；
6. service UUID 列表包含 HID / Battery / Device Information；
7. 不通过 `addServiceUUID()` 添加多个 16-bit 服务；
8. `DIAL_REPORT_ID == 1`；
9. 默认 report map 为 Radial Controller 最小描述符。

### 12.2 新增或更新 HID 描述符测试

测试应确认 descriptor byte sequence：

```python
assert b"\x05\x01\x09\x0E" in report_map  # Generic Desktop / System Multi-Axis Controller
assert b"\x85\x01" in report_map          # Report ID 1
assert b"\x05\x09\x09\x01" in report_map  # Button 1
assert b"\x05\x01\x09\x37" in report_map  # Dial
assert report_map[-1] == 0xC0
```

### 12.3 新增发送报告测试

如果项目当前测试框架支持静态分析，检查：

- 发送 report buffer 长度为 3；
- 第一个字节为 `DIAL_REPORT_ID`；
- dial payload 使用 15-bit；
- button 使用 bit0；
- notify 前调用 `setValue(report, sizeof(report))`。

### 12.4 运行测试

Agent 应运行项目已有测试命令。优先尝试：

```bash
pytest
```

如果项目测试命令不是 `pytest`，Agent 应检查 README、`pyproject.toml`、`package.json`、`Makefile` 或 CI 配置后选择正确命令。

---

## 13. 编译验证要求

Agent 应尝试执行固件编译。

优先查找项目已有说明，例如：

- README；
- `platformio.ini`；
- Arduino CLI 配置；
- CI workflow。

如果是 Arduino CLI 项目，优先尝试类似：

```bash
arduino-cli compile --fqbn esp32:esp32:esp32s3 .
```

实际 FQBN 以项目配置为准。

如果是 PlatformIO 项目，尝试：

```bash
pio run
```

如果无法确定编译命令，Agent 应记录：

```text
[BLOCKED] Cannot determine firmware build command.
```

并说明已检查哪些文件。

---

## 14. 不进入手写 GATT 的条件

本轮优先不重写 HID GATT Service。

只有在完成以上修改后，仍发现以下情况，才进入下一阶段“绕过 BLEHIDDevice 手写 GATT 服务”：

- Report Map `0x2A4B` 读出为空；
- Report Reference `0x2908` 不存在或读出错误；
- CCCD `0x2902` 不存在；
- Protocol Mode `0x2A4E` 不存在；
- HID Information `0x2A4A` 不存在；
- `BLEHIDDevice` 无法稳定注册必要 characteristic / descriptor。

如果进入下一阶段，应另开分支：

```bash
git checkout -b experiment/manual-hogp-service
```

不要在本修复分支中直接大规模重写。

---

## 15. 推荐分支与提交

### 15.1 分支名

```bash
git checkout -b fix/windows-hogp-enumeration
```

### 15.2 提交拆分建议

建议拆成 3 个提交：

```bash
git add esp32s3_touch_dial.ino
git commit -m "fix(ble): use bonded security for HID over GATT"

git add esp32s3_touch_dial.ino
git commit -m "fix(hid): use minimal radial controller report map"

git add tests tools docs
git commit -m "test(ble): validate HOGP advertising and report layout"
```

如果项目较小，也可以合并成一个提交：

```bash
git commit -m "fix: improve ESP32 BLE HID radial controller enumeration"
```

---

## 16. 完成后的输出格式

Agent 完成后应输出：

```text
Summary:
- Changed BLE security from NO_BOND to bonded Just Works.
- Restored Report ID 1 and minimal Radial Controller report map.
- Added HID/Battery/DIS 16-bit UUID advertising.
- Patched 0x2908 / 0x2902 descriptor permissions.
- Updated report sender to 3-byte Radial Controller format.
- Added/updated tests.

Validation:
- <test command>: PASS/FAIL
- <firmware compile command>: PASS/FAIL
- Report map size: <n>
- Adv primary data estimated length: <n>
- Known remaining risks: <items>
```

如果某项失败，必须写明：

```text
Failed:
- command:
- error:
- likely cause:
- next action:
```

---

## 17. 本轮成功标准

代码层面完成以下项目即可视为本轮成功：

- BLE security 使用 bond-capable Just Works；
- 不再使用 `NO_BOND` 作为主路径；
- 地址稳定；
- 广告短且包含 `1812 / 180F / 180A`；
- Report ID 为 1；
- Report Map 是最小 Radial Controller；
- Input Report 的 `2908` 与 `2902` 权限被显式修复；
- 发送报告为 3 字节；
- 测试覆盖以上核心点；
- 固件可以编译，或明确记录编译阻塞原因。

---

## 18. 备注

此任务书只覆盖 ESP32 项目侧修复。

主机端行为、Windows 端缓存、Windows 设备管理器、Windows 删除设备等操作不在本文件范围内。
