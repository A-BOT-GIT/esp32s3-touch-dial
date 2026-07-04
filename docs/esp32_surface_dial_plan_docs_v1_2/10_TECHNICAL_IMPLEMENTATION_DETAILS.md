# 10 技术实现细节：ESP32 固件实现方案

版本：v1.2

## 1. 目标

本文件把计划中的“做 Radial Controller MVP”拆成更具体的代码实现细节，便于 agent 直接改项目。

目标是把当前稳定的 BLE HID 初始化底座改造成：

```text
ESP32-S3 BLE HID Windows Radial Controller
```

不是：

```text
Consumer Control Media Dial
```

---

## 2. 建议模块拆分

如果当前项目仍集中在 `esp32s3_touch_dial.ino`，可以先不强制拆文件。但建议逻辑上按下面模块划分：

```text
BLE 初始化层
  - BLEDevice init
  - BLESecurity
  - stable random static address
  - HID service
  - DIS service
  - Battery service
  - advertising

HID descriptor 层
  - radialControllerReportMap
  - RADIAL_REPORT_ID
  - ReportRef / CCCD permission patch

Radial report 层
  - buildRadialPayload()
  - sendRadialReport()
  - last_send_type / last_backend_error

输入事件层
  - encoder rotation
  - button down
  - button up
  - long press tracking
  - touch button, if any

诊断层
  - HID_STATUS
  - ENC_STATUS
  - startup logs
  - per-report logs
```

后续可拆成：

```text
src/ble_hid_radial.h
src/ble_hid_radial.cpp
src/encoder_input.h
src/encoder_input.cpp
```

但 MVP 阶段可以先保持 `.ino`，减少构建风险。

---

## 3. BLE 初始化调用顺序

推荐顺序：

```cpp
void beginDialBackend() {
  Serial.println("[BLE-HID] init start");

  configureStableBleAddress();
  BLEDevice::init(BLE_PRODUCT_NAME);

  configureBleSecurity();
  configureBleEncryptionLevelPolicy();

  BLEServer* server = BLEDevice::createServer();
  server->setCallbacks(new DialBleServerCallbacks());

  BLEHIDDevice* hid = new BLEHIDDevice(server);

  hid->manufacturer()->setValue("zza");
  hid->pnp(0x02, 0x303A, 0x1001, 0x0100);
  hid->hidInfo(0x00, 0x01);

  bleRadialInputReport = hid->inputReport(RADIAL_REPORT_ID);
  fixHogpInputReportPermissions(bleRadialInputReport);

  hid->reportMap((uint8_t*)radialControllerReportMap,
                 sizeof(radialControllerReportMap));

  hid->startServices();

  configureBatteryServiceIfPresent();
  configureAdvertising();
  BLEDevice::startAdvertising();

  Serial.println("[BLE-HID] advertising started");
}
```

关键点：

```text
1. BLESecurity 在 createServer / startServices 前配置。
2. inputReport() 创建后立刻 patch 2908/2902 权限。
3. reportMap() 在 startServices() 前设置。
4. startServices() 后再 advertising。
5. 不要默认 setEncryptionLevel。
```

---

## 4. BLE security 实现细节

### 4.1 推荐代码

```cpp
static void configureBleSecurity() {
  BLESecurity* bleSecurity = new BLESecurity();

  bleSecurity->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
  bleSecurity->setCapability(ESP_IO_CAP_NONE);
  bleSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
  bleSecurity->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
  bleSecurity->setKeySize(16);

  Serial.println("[BLE-HID] security: SC_BOND + IO_NONE");
}
```

如果 Arduino/ESP32 版本不支持 `ESP_LE_AUTH_REQ_SC_BOND`，fallback：

```cpp
bleSecurity->setAuthenticationMode(ESP_LE_AUTH_BOND);
Serial.println("[BLE-HID] security: BOND + IO_NONE fallback");
```

### 4.2 强制加密策略

```cpp
#ifndef BLE_FORCE_ENCRYPTION_LEVEL
#define BLE_FORCE_ENCRYPTION_LEVEL 0
#endif

static void configureBleEncryptionLevelPolicy() {
#if BLE_FORCE_ENCRYPTION_LEVEL
  BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
  Serial.println("[BLE-HID] force encryption level: enabled");
#else
  Serial.println("[BLE-HID] force encryption level: disabled");
#endif
}
```

默认必须是：

```cpp
#define BLE_FORCE_ENCRYPTION_LEVEL 0
```

原因：实测中强制 setEncryptionLevel 会造成 Windows / ESP32 bond 状态不一致，出现反复断连。

---

## 5. 稳定 BLE 地址策略

目标：避免每次刷机地址变化，同时允许实验分支通过扰动最后一字节避开 Windows GATT 缓存。

```cpp
#ifndef BLE_IDENTITY_SUFFIX
#define BLE_IDENTITY_SUFFIX 0x31  // Radial MVP
#endif

static void fillBleDialRandomAddress(uint8_t addr[6]) {
  uint8_t baseMac[6] = {0};

  esp_err_t err = esp_read_mac(baseMac, ESP_MAC_BT);
  if (err != ESP_OK) {
    err = esp_read_mac(baseMac, ESP_MAC_WIFI_STA);
  }

  // random static address: top two bits of first byte must be 1
  addr[0] = baseMac[0] | 0xC0;
  addr[1] = baseMac[1];
  addr[2] = baseMac[2];
  addr[3] = baseMac[3];
  addr[4] = baseMac[4];
  addr[5] = baseMac[5] ^ BLE_IDENTITY_SUFFIX;

  Serial.printf("[BLE-HID] address: %02X:%02X:%02X:%02X:%02X:%02X\n",
                addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);
}
```

不同分支：

```text
Media Dial NE     BLE_IDENTITY_SUFFIX=0x24
Radial MVP        BLE_IDENTITY_SUFFIX=0x31
Radial MVP2       BLE_IDENTITY_SUFFIX=0x32
Haptic experiment BLE_IDENTITY_SUFFIX=0x41
```

---

## 6. Advertising 技术细节

继续使用短 16-bit UUID 广告，不要用多个 `addServiceUUID()` 堆到 31 字节外。

建议 AD：

```cpp
uint8_t serviceData[] = {
  0x07, 0x03,
  0x12, 0x18,  // HID 1812
  0x0F, 0x18,  // Battery 180F
  0x0A, 0x18   // Device Information 180A
};
```

名称放 scan response：

```text
ESP32-S3 Radial MVP
```

Appearance 可以保留 HID 类相关值，但不要依赖 Appearance 让 Windows 识别 Radial。关键还是 HID Report Map。

---

## 7. HID service 结构

Radial MVP 中只需要一个 Input Report characteristic：

```text
HID Service 0x1812
  Report Map
  HID Information
  HID Control Point
  Protocol Mode
  Report characteristic:
    Report ID = 1
    Report Type = Input
    CCCD = 0x2902
    Report Reference = 0x2908 = 01 01
```

不要同时保留 Media Report ID 2。

---

## 8. ReportRef / CCCD 权限 patch

目标：

```text
2908 readable
2902 readable/writable
```

伪代码：

```cpp
static void fixHogpInputReportPermissions(BLECharacteristic* inputReport) {
  if (!inputReport) return;

  BLEDescriptor* reportRef = inputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2908));
  if (reportRef) {
    reportRef->setAccessPermissions(ESP_GATT_PERM_READ);
  }

  BLEDescriptor* cccd = inputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
  if (cccd) {
    cccd->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
  }

  Serial.printf("[BLE-HID] radial descriptor permissions patched: 2908=%s, 2902=%s\n",
                reportRef ? "yes" : "no",
                cccd ? "yes" : "no");
}
```

如果当前 Arduino BLE 库没有 `getDescriptorByUUID()`，保留项目现有能工作的 patch 方式，不要为了重构破坏它。

---

## 9. Radial report 发送路径

### 9.1 全局状态

```cpp
static BLECharacteristic* bleRadialInputReport = nullptr;
static bool bleDialConnected = false;
static bool radialButtonPressed = false;
```

### 9.2 发送函数必须返回 bool

```cpp
static bool sendRadialReport(bool pressed, int16_t delta) {
  if (!bleDialConnected) {
    Serial.printf(">BLE radial report skip reason=not_connected button=%d delta=%d\n",
                  pressed ? 1 : 0, delta);
    return false;
  }

  if (!bleRadialInputReport) {
    Serial.printf(">BLE radial report skip reason=no_report button=%d delta=%d\n",
                  pressed ? 1 : 0, delta);
    return false;
  }

  uint16_t payload = buildRadialPayload(pressed, delta);
  uint8_t report[2] = {
    (uint8_t)(payload & 0xFF),
    (uint8_t)((payload >> 8) & 0xFF)
  };

  bleRadialInputReport->setValue(report, sizeof(report));
  bleRadialInputReport->notify();

  Serial.printf(">BLE radial report len=2 data=%02X %02X button=%d delta=%d hid=sent\n",
                report[0], report[1], pressed ? 1 : 0, delta);
  return true;
}
```

---

## 10. 编码器映射

```cpp
void onEncoderRotate(int deltaSteps) {
  if (deltaSteps == 0) return;

  int16_t radialDelta = (deltaSteps > 0)
      ? RADIAL_DELTA_UNIT
      : -RADIAL_DELTA_UNIT;

  bool ok = sendRadialReport(radialButtonPressed, radialDelta);

  Serial.printf(">ENC source=ENC dir=%s radial_delta=%d hid=%s ready=%s backend=ble_hid_radial\n",
                deltaSteps > 0 ? "RIGHT" : "LEFT",
                radialDelta,
                ok ? "sent" : "skip",
                bleDialConnected ? "yes" : "no");
}
```

---

## 11. 按键映射

```cpp
void onEncoderButtonDown() {
  if (radialButtonPressed) return;
  radialButtonPressed = true;
  bool ok = sendRadialReport(true, 0);
  Serial.printf(">ENC_BUTTON down hid=%s\n", ok ? "sent" : "skip");
}

void onEncoderButtonUp() {
  if (!radialButtonPressed) return;
  radialButtonPressed = false;
  bool ok = sendRadialReport(false, 0);
  Serial.printf(">ENC_BUTTON up hid=%s\n", ok ? "sent" : "skip");
}
```

不要：

```cpp
sendMute();
sendPlayPause();
```

---

## 12. 长按逻辑

Surface Dial 菜单由 Windows 解释 button hold，不是固件主动发媒体键。

长按期间固件应保持：

```text
button=1
```

直到释放。

可打印：

```cpp
if (!longPressLogged && radialButtonPressed && millis() - downMs > 800) {
  longPressLogged = true;
  Serial.println(">ENC_BUTTON hold candidate for radial menu");
}
```

但不要发送新的 HID usage。

---

## 13. 构建和测试

```bash
arduino-cli compile --fqbn esp32:esp32:esp32s3 .
pytest -q
```

如果有 USB+CDC 独立构建，也必须跑。

---

## 14. 最小实机成功日志

```text
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
[BLE-HID] radial report id: 1
[BLE-HID] radial report ref: 01 01
>BLE radial report len=2 data=02 00 button=0 delta=1 hid=sent
>BLE radial report len=2 data=FE FF button=0 delta=-1 hid=sent
>BLE radial report len=2 data=01 00 button=1 delta=0 hid=sent
>BLE radial report len=2 data=00 00 button=0 delta=0 hid=sent
```
