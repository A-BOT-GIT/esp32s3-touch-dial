/*
 * ESP32-S3 Touch Dial — wired serial + display + CST816S touch MVP
 *
 * Hardware wiring currently used:
 *   LCD GC9A01: MOSI=GPIO10, SCLK=GPIO11, CS=GPIO9, DC=GPIO12,
 *                RST=GPIO13, BL=GPIO7, MISO not connected
 *   Touch CST816S: TP_SDA=GPIO4, TP_SCL=GPIO5, TP_INT=GPIO6,
 *                  TP_RST=GPIO8
 *
 * Protocol:
 *   >HELLO          wait PC ACK
 *   >PING           heartbeat, wait PC ACK
 *   >MODE wired     wired mode entered
 *   >VOLUME N       absolute volume 0~100
 *   >PRESS          center short tap
 *   >MUTE_TOGGLE    center long press
 */

#include <Arduino.h>
#include <Adafruit_GC9A01A.h>
#include <Wire.h>
#include <math.h>
#if ARDUINO_USB_MODE
#include "HWCDC.h"
#if defined(CONFIG_BLUEDROID_ENABLED)
#include "BLEAdvertising.h"
#include "BLEDevice.h"
#include "BLEHIDDevice.h"
#include "BLESecurity.h"
#include "BLEServer.h"
#include <esp_random.h>
#endif
#else
#include "USB.h"
#include "USBHID.h"
#endif

// 控制通道选择原则：
// 1) 不依赖 COM 编号；优先让“当前 native USB CDC 身份”承载协议。
// 2) hwcdc 构建：协议走 USBSerial（Windows 会给它一个会变化的 COMx）。
// 3) tinyusb + cdc_on_boot：协议走 Serial（此时 Serial 就是 USB CDC）。
// 4) tinyusb 且未启用 cdc_on_boot：只能退回 UART0。
#if ARDUINO_USB_MODE
#define DIAL_SERIAL USBSerial
#define DIAL_CONTROL_CHANNEL_NAME "native_usb_hwcdc"
#define DIAL_USB_MODE_NAME "hwcdc"
#elif ARDUINO_USB_CDC_ON_BOOT
#define DIAL_SERIAL Serial
#define DIAL_CONTROL_CHANNEL_NAME "native_usb_tinyusb_cdc"
#define DIAL_USB_MODE_NAME "tinyusb"
#else
#define DIAL_SERIAL Serial
#define DIAL_CONTROL_CHANNEL_NAME "uart0_fallback"
#define DIAL_USB_MODE_NAME "tinyusb"
#endif

namespace {

void probeLog(const char* tag) {
  DIAL_SERIAL.print(">PROBE ");
  DIAL_SERIAL.println(tag);
}

// Display pins
constexpr int8_t PIN_LCD_MISO = -1;
constexpr uint8_t PIN_LCD_MOSI = 10;
constexpr uint8_t PIN_LCD_SCLK = 11;
constexpr uint8_t PIN_LCD_CS = 9;
constexpr uint8_t PIN_LCD_DC = 12;
constexpr uint8_t PIN_LCD_RST = 13;
constexpr uint8_t PIN_LCD_BL = 7;

// Touch pins
constexpr uint8_t PIN_TP_SDA = 4;
constexpr uint8_t PIN_TP_SCL = 5;
constexpr uint8_t PIN_TP_INT = 6;
constexpr uint8_t PIN_TP_RST = 8;
constexpr uint8_t CST816_ADDR = 0x15;

// Encoder pins (planned hardware path; can also be simulated from serial)
constexpr uint8_t PIN_ENC_CLK = 14;
constexpr uint8_t PIN_ENC_DT = 15;
constexpr uint8_t PIN_ENC_SW = 16;
constexpr int ENCODER_STEP = 2;
constexpr unsigned long ENCODER_UI_HOLD_MS = 800;

constexpr int CX = 120;
constexpr int CY = 120;
constexpr int RING_INNER = 70;
constexpr int RING_OUTER = 125;
constexpr int CENTER_RADIUS = 55;

constexpr unsigned long HELLO_INTERVAL_MS = 500;
constexpr unsigned long PING_INTERVAL_MS = 2000;
constexpr unsigned long ACK_TIMEOUT_MS = 60000;
constexpr unsigned long TOUCH_POLL_MS = 20;
constexpr unsigned long TOUCH_RAW_DEBUG_MS = 500;
constexpr unsigned long VOLUME_SEND_MIN_MS = 50;
constexpr unsigned long BLE_ROTATE_SEND_MIN_MS = 40;
constexpr unsigned long BLE_PRESS_SEND_MIN_MS = 120;
constexpr unsigned long TAP_MAX_MS = 550;
constexpr unsigned long LONG_PRESS_MS = 850;
constexpr unsigned long PRESS_DEBOUNCE_MS = 300;

constexpr uint8_t DIAL_REPORT_ID = 1;  // Radial Controller requires non-zero Report ID
constexpr uint8_t MEDIA_REPORT_ID = 2;  // Consumer Control volume test
constexpr uint8_t DIAL_BUTTON_PRESS = 0x01;
constexpr int8_t DIAL_ROTATE_RIGHT = 1;
constexpr int8_t DIAL_ROTATE_LEFT = -1;

// BLE HID identity — extracted constants for minimal tuning rounds.
// Do not change behavior unless the descriptor profile selector is switched.
// Round 1 result: HID_JOYSTICK (0x03C3) did not improve connection stability.
// Reverted to GENERIC_HID (0x03C0) baseline. Proceeding to Round 2 descriptor tuning.
constexpr uint16_t BLE_DIAL_APPEARANCE = 0x03C0;  // GENERIC_HID

// BLE HID descriptor profile switch — change here to test identity variant.
enum class BleDialDescriptorProfile : uint8_t {
  Baseline = 0,   // Minimal Radial Controller (System Multi-Axis + Dial + Button)
  VariantA = 1,   // placeholder
  VariantB = 2,   // placeholder
};
// Default: Radial Controller minimal descriptor per task doc.
constexpr BleDialDescriptorProfile BLE_DIAL_DESCRIPTOR_PROFILE = BleDialDescriptorProfile::Baseline;

// Consumer Control report map: Volume+/-, Play/Pause, Mute.
// Report ID 2, 4×1-bit buttons in a single Input + 4-bit padding = 1 byte.
static const uint8_t mediaReportMap[] = {
  0x05, 0x0C,              // Usage Page (Consumer)
  0x09, 0x01,              // Usage (Consumer Control)
  0xA1, 0x01,              // Collection (Application)
  0x85, MEDIA_REPORT_ID,   //   Report ID (2)
  0x09, 0xE9,              //   Usage (Volume Increment)
  0x09, 0xEA,              //   Usage (Volume Decrement)
  0x09, 0xCD,              //   Usage (Play/Pause)
  0x09, 0xE2,              //   Usage (Mute)
  0x15, 0x00,              //   Logical Minimum (0)
  0x25, 0x01,              //   Logical Maximum (1)
  0x75, 0x01,              //   Report Size (1)
  0x95, 0x04,              //   Report Count (4)
  0x81, 0x02,              //   Input (Data, Var, Abs)
  0x75, 0x01,              //   Report Size (1)
  0x95, 0x04,              //   Report Count (4)
  0x81, 0x03,              //   Input (Const, Var, Abs) padding
  0xC0                     // End Collection
};

// Minimal Radial Controller report map (kept for reference).
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

// Alias for descriptor selector.
static const uint8_t dial_report_descriptor[] = {
  // Stub — use radialControllerReportMap directly.
};
static const uint8_t dial_report_descriptor_variant_a[] = {
  // Stub — placeholder.
};

// Returns the report descriptor for the currently selected profile.
static const uint8_t* getDialReportDescriptor(uint16_t& outLen) {
  (void)dial_report_descriptor;
  (void)dial_report_descriptor_variant_a;
  (void)radialControllerReportMap;
  outLen = sizeof(mediaReportMap);
  return mediaReportMap;
}

bool dialBackendReady();
bool bleDialBackendBegun = false;
#if ARDUINO_USB_MODE && defined(CONFIG_BLUEDROID_ENABLED)
enum class BleDialState : uint8_t {
  Uninitialized = 0,
  Initializing,
  Advertising,
  ConnectedIdle,
  SendingRotate,
  SendingPress,
  RestartingAdvertising,
  Error,
};

BLEServer* bleDialServer = nullptr;
BLEHIDDevice* bleDialHid = nullptr;
BLEAdvertising* bleDialAdvertising = nullptr;
BLECharacteristic* bleDialInputReport = nullptr;
BLECharacteristic* bleMediaInputReport = nullptr;  // Consumer Control volume test
esp_bd_addr_t bleDialRandomAddress = {0};
bool bleDialConnected = false;
bool bleDialAdvertisingActive = false;
BleDialState bleDialState = BleDialState::Uninitialized;
const char* bleLastBackendError = "none";
const char* bleLastSendType = "none";
unsigned long bleLastSendMs = 0;
unsigned long bleLastRotateSendMs = 0;
unsigned long bleLastPressSendMs = 0;
#endif

const char* dialBackendName() {
#if !ARDUINO_USB_MODE
  return "usb_hid_tinyusb";
#else
  return "ble_hid_dial";
#endif
}

#if ARDUINO_USB_MODE && defined(CONFIG_BLUEDROID_ENABLED)
void fillBleDialRandomAddress(esp_bd_addr_t addr) {
  // Derive stable random static address from BT base MAC.
  // Fall back to WiFi STA MAC if BT MAC unavailable.
  uint8_t baseMac[6] = {0};
  esp_err_t err = esp_read_mac(baseMac, ESP_MAC_BT);
  if (err != ESP_OK) {
    esp_read_mac(baseMac, ESP_MAC_WIFI_STA);
  }
  memcpy(addr, baseMac, 6);
  // TEST BRANCH: XOR byte 5 so Windows sees a different BLE address
  // and does not reuse cached GATT/HID state from the radial-controller build.
  addr[5] ^= 0x24;
  // BLE random static address: top two bits of byte 0 must be 11.
  addr[0] = static_cast<uint8_t>(addr[0] | 0xC0);
}

const char* bleDialStateName() {
  switch (bleDialState) {
    case BleDialState::Uninitialized:
      return "uninitialized";
    case BleDialState::Initializing:
      return "initializing";
    case BleDialState::Advertising:
      return "advertising";
    case BleDialState::ConnectedIdle:
      return "connected_idle";
    case BleDialState::SendingRotate:
      return "sending_rotate";
    case BleDialState::SendingPress:
      return "sending_press";
    case BleDialState::RestartingAdvertising:
      return "restarting_advertising";
    case BleDialState::Error:
      return "error";
    default:
      return "unknown";
  }
}

void setBleDialState(BleDialState nextState) {
  bleDialState = nextState;
}

void setBleLastBackendError(const char* error) {
  bleLastBackendError = (error && error[0]) ? error : "none";
}

void setBleLastSendType(const char* sendType) {
  bleLastSendType = (sendType && sendType[0]) ? sendType : "none";
  bleLastSendMs = millis();
}

void resetBleDialSendTracking() {
  bleLastSendType = "none";
  bleLastBackendError = "none";
  bleLastSendMs = 0;
  bleLastRotateSendMs = 0;
  bleLastPressSendMs = 0;
}

void logBleEvent(const char* event, const char* detail = nullptr) {
  if (detail && detail[0]) {
    DIAL_SERIAL.printf(">BLE %s %s\n", event, detail);
  } else {
    DIAL_SERIAL.printf(">BLE %s\n", event);
  }
}

void restoreBleDialStableState() {
  if (bleDialConnected) {
    setBleDialState(BleDialState::ConnectedIdle);
  } else if (bleDialAdvertisingActive) {
    setBleDialState(BleDialState::Advertising);
  }
}

// Consumer Control button mapping.
// Volume Up=0x01, Volume Down=0x02, Play/Pause=0x04, Mute=0x08.
static uint8_t mediaBitsForDelta(int8_t delta) {
  if (delta > 0) return 0x01;  // Volume Increment
  if (delta < 0) return 0x02;  // Volume Decrement
  return 0x00;
}

static void sendMediaKey(uint8_t bits, const char* action) {
  if (!bleDialConnected || !bleMediaInputReport) return;
  uint8_t report[1] = {bits};
  bleMediaInputReport->setValue(report, sizeof(report));
  bleMediaInputReport->notify();
  DIAL_SERIAL.printf(">BLE media report len=1 data=%02X action=%s hid=sent\n", bits, action);
  delay(80);
  uint8_t release[1] = {0x00};
  bleMediaInputReport->setValue(release, sizeof(release));
  bleMediaInputReport->notify();
  DIAL_SERIAL.printf(">BLE media report len=1 data=00 action=release hid=sent\n");
}

static void sendVolumeUp()    { sendMediaKey(0x01, "volume_up"); }
static void sendVolumeDown()  { sendMediaKey(0x02, "volume_down"); }
static void sendPlayPause()   { sendMediaKey(0x04, "play_pause"); }
static void sendMute()        { sendMediaKey(0x08, "mute"); }

bool bleDialSendReleaseReport() {
  if (bleMediaInputReport == nullptr) {
    setBleLastBackendError("report_missing");
    restoreBleDialStableState();
    return false;
  }
  delay(80);
  uint8_t releaseReport[1] = {0x00};
  bleMediaInputReport->setValue(releaseReport, sizeof(releaseReport));
  bleMediaInputReport->notify();
  DIAL_SERIAL.printf(">BLE media report len=1 data=00 action=release hid=sent\n");
  return true;
}

bool bleDialIsPressSendType(const char* sendType) {
  return sendType && sendType[0] == 'p';
}

bool bleDialSendReport(uint8_t buttons, int8_t delta, const char* sendType) {
  setBleLastSendType(sendType);
  if (!dialBackendReady() || bleMediaInputReport == nullptr) {
    const char* skipReason = bleMediaInputReport == nullptr ? "report_missing" : "not_ready";
    setBleLastBackendError(skipReason);
    logBleEvent("report", bleMediaInputReport == nullptr ? "skip reason=report_missing" : "skip reason=not_ready");
    restoreBleDialStableState();
    return false;
  }

  bool isPress = bleDialIsPressSendType(sendType);
  unsigned long now = millis();
  unsigned long* lastSendSlot = isPress ? &bleLastPressSendMs : &bleLastRotateSendMs;
  unsigned long minInterval = isPress ? BLE_PRESS_SEND_MIN_MS : BLE_ROTATE_SEND_MIN_MS;
  if (*lastSendSlot != 0 && now - *lastSendSlot < minInterval) {
    const char* skipReason = isPress ? "rate_limited_press" : "rate_limited_rotate";
    setBleLastBackendError(skipReason);
    logBleEvent("report", isPress ? "skip reason=rate_limited_press" : "skip reason=rate_limited_rotate");
    restoreBleDialStableState();
    return false;
  }

  *lastSendSlot = now;
  setBleLastBackendError("none");

  if (isPress) {
    sendPlayPause();
  } else {
    if (delta > 0) sendVolumeUp();
    else if (delta < 0) sendVolumeDown();
  }

  restoreBleDialStableState();
  return true;
}
#endif

// Media key stubs for USB builds (ARDUINO_USB_MODE=0).
// Real implementations inside the BLE block (ARDUINO_USB_MODE=1) override these.
#if !ARDUINO_USB_MODE
static void sendMediaKey(uint8_t, const char*) {}
static void sendVolumeUp()    {}
static void sendVolumeDown()  {}
static void sendPlayPause()   {}
static void sendMute()        {}
#endif

const char* dialBackendStatus() {
#if !ARDUINO_USB_MODE
  return dialBackendReady() ? "ready" : "waiting_for_usb_host";
#elif defined(CONFIG_BLUEDROID_ENABLED)
  return bleDialStateName();
#else
  return bleDialBackendBegun ? "bt_stack_unavailable" : "stub_uninitialized";
#endif
}

const char* dialBackendNote() {
#if !ARDUINO_USB_MODE
  return "usb_tinyusb_custom_hid";
#elif defined(CONFIG_BLUEDROID_ENABLED)
  if (bleDialConnected) return "ble_dial_link_established";
  if (bleDialAdvertisingActive) return "ble_dial_advertising";
  if (bleDialState == BleDialState::Initializing) return "ble_dial_initializing";
  if (bleDialState == BleDialState::Error) return bleLastBackendError;
  return "ble_dial_backend_waiting_for_connection";
#else
  return "ble_stack_disabled_in_build";
#endif
}

#if !ARDUINO_USB_MODE
USBHID HID;

class DialHIDDevice : public USBHIDDevice {
 public:
  DialHIDDevice() {
    static bool initialized = false;
    if (!initialized) {
      initialized = true;
      uint16_t descLen = 0;
      getDialReportDescriptor(descLen);
      HID.addDevice(this, descLen);
    }
  }

  void begin() { HID.begin(); }

  uint16_t _onGetDescriptor(uint8_t* buffer) override {
    uint16_t descriptorLen = 0;
    const uint8_t* desc = getDialReportDescriptor(descriptorLen);
    memcpy(buffer, desc, descriptorLen);
    return descriptorLen;
  }

  bool sendReport(uint8_t buttons, int8_t delta) {
    uint8_t report[3];
    report[0] = DIAL_REPORT_ID;
    bool pressed = (buttons & DIAL_BUTTON_PRESS) != 0;
    int16_t dial15 = static_cast<int16_t>(delta) * 10;
    if (dial15 < -3600) dial15 = -3600;
    if (dial15 >  3600) dial15 =  3600;
    uint16_t dialBits = static_cast<uint16_t>(dial15) & 0x7FFF;
    uint16_t payload = static_cast<uint16_t>((dialBits << 1) | (pressed ? 1 : 0));
    report[1] = static_cast<uint8_t>(payload & 0xFF);
    report[2] = static_cast<uint8_t>((payload >> 8) & 0xFF);
    return HID.SendReport(DIAL_REPORT_ID, report, sizeof(report));
  }
};

DialHIDDevice dialHid;
#elif defined(CONFIG_BLUEDROID_ENABLED)
void printUsbHidStatus(const char* reason);
extern bool usbHidReadySeen;

class DialBleServerCallbacks : public BLEServerCallbacks {
 public:
  void onConnect(BLEServer* pServer) override {
    (void)pServer;
    bleDialConnected = true;
    bleDialAdvertisingActive = false;
    resetBleDialSendTracking();
    setBleDialState(BleDialState::ConnectedIdle);
    usbHidReadySeen = false;
    logBleEvent("connected");
    DIAL_SERIAL.println("[BLE-HID] connected");
    printUsbHidStatus("ble_connect");
  }

  void onDisconnect(BLEServer* pServer) override {
    bleDialConnected = false;
    DIAL_SERIAL.println("[BLE-HID] disconnected");
    usbHidReadySeen = false;
    resetBleDialSendTracking();
    setBleDialState(BleDialState::RestartingAdvertising);
    if (pServer) {
      pServer->startAdvertising();
      bleDialAdvertisingActive = true;
      setBleDialState(BleDialState::Advertising);
    }
    logBleEvent("disconnected");
    logBleEvent("advertising", "restart");
    printUsbHidStatus("ble_disconnect");
  }
};
#endif

Adafruit_GC9A01A tft(PIN_LCD_CS,
                     PIN_LCD_DC,
                     PIN_LCD_MOSI,
                     PIN_LCD_SCLK,
                     PIN_LCD_RST,
                     PIN_LCD_MISO);
GFXcanvas16* frame = nullptr;

bool wired = false;
bool touchPresent = false;
unsigned long lastHelloMs = 0;
unsigned long lastPingMs = 0;
unsigned long lastAckMs = 0;
unsigned long lastTouchPollMs = 0;
unsigned long lastTouchRawDebugMs = 0;
unsigned long lastVolumeSendMs = 0;
int currentVolume = 50;
int lastSentVolume = -1;
int drawnVolume = -1;

char rxLine[32];
size_t rxLen = 0;

struct TouchPoint {
  bool touched = false;
  uint16_t x = 0;
  uint16_t y = 0;
};

bool wasTouching = false;
bool centerCandidate = false;
bool longPressSent = false;
unsigned long touchDownMs = 0;
unsigned long lastPressMs = 0;
bool bootModeSent = false;

char uiModeText[16] = "BOOT";
char uiDebugText[24] = "ENC IDLE";
unsigned long uiDebugUntilMs = 0;
bool usbHidReadySeen = false;
bool usbStartedSeen = false;

static const int8_t ENC_TABLE[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
volatile int sEncDir = 0;
volatile int8_t sEncState = 0;
bool sEncSwitchWasLow = false;
unsigned long encSwitchDownMs = 0;
bool encLongPressSent = false;

// EXPERIMENT: no forced encryption. Name changed to avoid Windows cache.
constexpr char USB_PRODUCT_NAME[] = "ESP32-S3 Media Dial NE";

// Set to 1 to force encryption on connect (may cause disconnect storm).
#define BLE_FORCE_ENCRYPTION_LEVEL 0
constexpr char USB_MANUFACTURER_NAME[] = "zza";
constexpr uint16_t USB_FW_VERSION_BCD = 0x0100;

// BLE HID device info — extracted for metadata tuning rounds.
constexpr uint8_t  BLE_PNP_SIG     = 0x02;    // 0x02 = USB
constexpr uint16_t BLE_PNP_VID     = 0x303A;   // Espressif
constexpr uint16_t BLE_PNP_PID     = 0x1001;
constexpr uint8_t  BLE_HID_COUNTRY = 0x00;    // Not localized
constexpr uint8_t  BLE_HID_FLAGS   = 0x01;    // RemoteWake + NormallyConnectable

uint16_t volumeColor(int volume) {
  (void)volume;
  // Use one stable active color. Previous threshold colors made the arc look
  // like blue/green segments were offset after frequent redraws.
  return GC9A01A_YELLOW;
}

void drawThickArcTo(Adafruit_GFX& gfx, int startDeg, int endDeg, int radius, int thickness, uint16_t color) {
  int step = (endDeg >= startDeg) ? 1 : -1;
  for (int deg = startDeg;; deg += step) {
    float rad = deg * PI / 180.0f;
    int x = CX + static_cast<int>(cos(rad) * radius);
    int y = CY + static_cast<int>(sin(rad) * radius);
    gfx.fillCircle(x, y, thickness / 2, color);
    if (deg == endDeg) break;
  }
}

void drawThickArc(int startDeg, int endDeg, int radius, int thickness, uint16_t color) {
  drawThickArcTo(tft, startDeg, endDeg, radius, thickness, color);
}

int volumeFillEnd(int volume) {
  constexpr int ARC_START = 135;
  constexpr int ARC_END = 405;
  volume = max(0, min(100, volume));
  return ARC_START + (ARC_END - ARC_START) * volume / 100;
}

void drawCenterUiTo(Adafruit_GFX& gfx, int volume, const char* modeText) {
  int16_t x1, y1;
  uint16_t w, h;

  gfx.fillCircle(CX, CY, 67, GC9A01A_BLACK);
  gfx.drawCircle(CX, CY, 68, GC9A01A_DARKGREY);

  gfx.setTextWrap(false);
  gfx.setTextColor(wired ? GC9A01A_GREEN : GC9A01A_YELLOW, GC9A01A_BLACK);
  gfx.setTextSize(2);
  gfx.getTextBounds(modeText, 0, 0, &x1, &y1, &w, &h);
  gfx.setCursor(CX - static_cast<int>(w) / 2, 60);
  gfx.print(modeText);

  char buf[8];
  snprintf(buf, sizeof(buf), "%d%%", volume);
  gfx.setTextColor(GC9A01A_WHITE, GC9A01A_BLACK);
  gfx.setTextSize(4);
  gfx.getTextBounds(buf, 0, 0, &x1, &y1, &w, &h);
  gfx.setCursor(CX - static_cast<int>(w) / 2, 98);
  gfx.print(buf);

  gfx.setTextColor(GC9A01A_CYAN, GC9A01A_BLACK);
  gfx.setTextSize(1);
  gfx.getTextBounds(uiDebugText, 0, 0, &x1, &y1, &w, &h);
  gfx.setCursor(CX - static_cast<int>(w) / 2, 148);
  gfx.print(uiDebugText);
}

void drawVolumeUi(int volume, const char* modeText, bool fullRedraw = false) {
  constexpr int ARC_START = 135;
  constexpr int ARC_END = 405;
  constexpr int ARC_RADIUS = 101;
  constexpr int ARC_THICKNESS = 14;

  volume = max(0, min(100, volume));
  int fillEnd = volumeFillEnd(volume);

  if (!fullRedraw && drawnVolume >= 0 && frame != nullptr) {
    int prevFillEnd = volumeFillEnd(drawnVolume);
    if (fillEnd > prevFillEnd) {
      drawThickArc(prevFillEnd + 1, fillEnd, ARC_RADIUS, ARC_THICKNESS, volumeColor(volume));
    } else if (fillEnd < prevFillEnd) {
      drawThickArc(prevFillEnd, fillEnd + 1, ARC_RADIUS, ARC_THICKNESS, GC9A01A_DARKGREY);
    }
    drawCenterUiTo(tft, volume, modeText);
    drawnVolume = volume;
    return;
  }

  // Full-screen states (boot / mode change / press / mute) still compose in RAM then
  // push once, but normal volume changes now update only the changed arc segment.
  frame->fillScreen(GC9A01A_BLACK);
  frame->setTextWrap(false);

  drawThickArcTo(*frame, ARC_START, ARC_END, ARC_RADIUS, ARC_THICKNESS, GC9A01A_DARKGREY);
  drawThickArcTo(*frame, ARC_START, fillEnd, ARC_RADIUS, ARC_THICKNESS, volumeColor(volume));
  drawCenterUiTo(*frame, volume, modeText);
  drawnVolume = volume;

  tft.drawRGBBitmap(0, 0, frame->getBuffer(), 240, 240);
}

void drawTouchDot(uint16_t x, uint16_t y) {
  tft.fillCircle(x, y, 4, GC9A01A_WHITE);
}

bool i2cWriteReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(CST816_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool i2cReadBytes(uint8_t reg, uint8_t* buf, size_t len) {
  Wire.beginTransmission(CST816_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  size_t got = Wire.requestFrom(static_cast<int>(CST816_ADDR), static_cast<int>(len));
  if (got != len) return false;
  for (size_t i = 0; i < len; i++) buf[i] = Wire.read();
  return true;
}

void resetTouch() {
  pinMode(PIN_TP_RST, OUTPUT);
  digitalWrite(PIN_TP_RST, LOW);
  delay(10);
  digitalWrite(PIN_TP_RST, HIGH);
  delay(50);
  pinMode(PIN_TP_INT, INPUT_PULLUP);
}

bool probeTouch() {
  Wire.beginTransmission(CST816_ADDR);
  if (Wire.endTransmission() != 0) return false;

  uint8_t chipId = 0;
  // 0xA7 is chip ID on common CST816S modules; failure is not fatal if addr ACKs.
  if (i2cReadBytes(0xA7, &chipId, 1)) {
    DIAL_SERIAL.printf(">I2C CST816S addr=0x%02X chip=0x%02X\n", CST816_ADDR, chipId);
  } else {
    DIAL_SERIAL.printf(">I2C CST816S addr=0x%02X chip=unknown\n", CST816_ADDR);
  }

  // Disable auto sleep where supported. Ignore failures.
  i2cWriteReg(0xFE, 0x01);
  // Enable common motion/IRQ modes on CST816S-compatible controllers.
  // Ignore NACKs: some variants do not implement every register.
  i2cWriteReg(0xEC, 0x01);  // motion mask / continuous report on some modules
  i2cWriteReg(0xFA, 0x01);  // IRQ control on some modules
  return true;
}

void scanI2C() {
  DIAL_SERIAL.print(">I2C scan");
  int found = 0;
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      DIAL_SERIAL.printf(" 0x%02X", addr);
      found++;
    }
  }
  DIAL_SERIAL.printf(" found=%d\n", found);
}

void dumpTouchRegs(const char* label) {
  uint8_t regs1[8] = {0};
  uint8_t regs2[8] = {0};
  uint8_t info[4] = {0};
  bool ok1 = i2cReadBytes(0x00, regs1, sizeof(regs1));
  bool ok2 = i2cReadBytes(0x01, regs2, sizeof(regs2));
  bool ok3 = i2cReadBytes(0xA7, info, sizeof(info));
  DIAL_SERIAL.printf(">I2C dump %s ok00=%d", label, ok1 ? 1 : 0);
  if (ok1) {
    DIAL_SERIAL.printf(" r00=%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X",
                  regs1[0], regs1[1], regs1[2], regs1[3], regs1[4], regs1[5], regs1[6], regs1[7]);
  }
  DIAL_SERIAL.printf(" ok01=%d", ok2 ? 1 : 0);
  if (ok2) {
    DIAL_SERIAL.printf(" r01=%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X",
                  regs2[0], regs2[1], regs2[2], regs2[3], regs2[4], regs2[5], regs2[6], regs2[7]);
  }
  DIAL_SERIAL.printf(" okA7=%d", ok3 ? 1 : 0);
  if (ok3) {
    DIAL_SERIAL.printf(" info=%02X,%02X,%02X,%02X", info[0], info[1], info[2], info[3]);
  }
  DIAL_SERIAL.println();
}

bool readTouch(TouchPoint& tp) {
  uint8_t data[7] = {0};
  if (!i2cReadBytes(0x01, data, sizeof(data))) {
    tp.touched = false;
    return false;
  }

  // CST816S common register map:
  // 0x01 gesture, 0x02 finger_num, 0x03 xh, 0x04 xl, 0x05 yh, 0x06 yl.
  // Because we read starting at 0x01: data[0]=gesture, data[1]=finger_num...
  uint8_t points = data[1] & 0x0F;
  bool allFF = true;
  for (uint8_t b : data) {
    if (b != 0xFF) {
      allFF = false;
      break;
    }
  }
  bool intLow = digitalRead(PIN_TP_INT) == LOW;
  unsigned long now = millis();
  if (allFF) {
    if (now - lastTouchRawDebugMs >= TOUCH_RAW_DEBUG_MS) {
      lastTouchRawDebugMs = now;
      DIAL_SERIAL.println(">TOUCH bus_ff data=FF,FF,FF,FF,FF,FF,FF");
      dumpTouchRegs("bus_ff");
    }
    tp.touched = false;
    return true;
  }
  if ((points > 0 || intLow) && false && now - lastTouchRawDebugMs >= TOUCH_RAW_DEBUG_MS) {
    lastTouchRawDebugMs = now;
    DIAL_SERIAL.printf(">TOUCH raw int=%d points=%u data=%02X,%02X,%02X,%02X,%02X,%02X,%02X\n",
                  intLow ? 0 : 1,
                  points,
                  data[0], data[1], data[2], data[3], data[4], data[5], data[6]);
  }

  if (points == 0) {
    if (false && now - lastTouchRawDebugMs >= 1000) {
      uint8_t regs0[16] = {0};
      i2cReadBytes(0x00, regs0, sizeof(regs0));
      lastTouchRawDebugMs = now;
      DIAL_SERIAL.printf(">TOUCH sample int=%d data=%02X,%02X,%02X,%02X,%02X,%02X,%02X r00=%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X\n",
                    intLow ? 0 : 1,
                    data[0], data[1], data[2], data[3], data[4], data[5], data[6],
                    regs0[0], regs0[1], regs0[2], regs0[3], regs0[4], regs0[5], regs0[6], regs0[7],
                    regs0[8], regs0[9], regs0[10], regs0[11], regs0[12], regs0[13], regs0[14], regs0[15]);
    }
    tp.touched = false;
    return true;
  }

  uint16_t x = ((data[2] & 0x0F) << 8) | data[3];
  uint16_t y = ((data[4] & 0x0F) << 8) | data[5];

  // Fallback for modules whose first useful byte is shifted by one.
  if (x > 240 || y > 240) {
    x = ((data[3] & 0x0F) << 8) | data[4];
    y = ((data[5] & 0x0F) << 8) | data[6];
  }

  if (x > 240 || y > 240) {
    DIAL_SERIAL.printf(">TOUCH invalid x=%u y=%u\n", x, y);
    tp.touched = false;
    return true;
  }

  tp.touched = true;
  tp.x = x;
  tp.y = y;
  return true;
}

int pointToVolume(uint16_t x, uint16_t y) {
  float dx = static_cast<float>(x) - CX;
  float dy = static_cast<float>(y) - CY;
  float r = sqrtf(dx * dx + dy * dy);
  if (r < RING_INNER || r > RING_OUTER) return -1;

  float deg = atan2f(dy, dx) * 180.0f / PI;
  if (deg < 0) deg += 360.0f;

  float progress = -1.0f;
  if (deg >= 135.0f && deg <= 360.0f) {
    progress = (deg - 135.0f) / 270.0f;
  } else if (deg >= 0.0f && deg <= 45.0f) {
    progress = (deg + 360.0f - 135.0f) / 270.0f;
  } else {
    return -1;
  }

  int volume = static_cast<int>(roundf(progress * 100.0f));
  return max(0, min(100, volume));
}

bool isCenter(uint16_t x, uint16_t y) {
  int dx = static_cast<int>(x) - CX;
  int dy = static_cast<int>(y) - CY;
  return dx * dx + dy * dy <= CENTER_RADIUS * CENTER_RADIUS;
}

const char* currentModeText() {
  return uiModeText;
}

void setModeText(const char* text) {
  snprintf(uiModeText, sizeof(uiModeText), "%s", text);
}

void setDebugText(const char* source, const char* direction, bool active) {
  snprintf(uiDebugText, sizeof(uiDebugText), "%s %s %s", source, direction, active ? "RUN" : "IDLE");
  uiDebugUntilMs = millis() + ENCODER_UI_HOLD_MS;
}

void refreshIdleDebugIfNeeded() {
  if (uiDebugUntilMs == 0) return;
  if (millis() < uiDebugUntilMs) return;
  uiDebugUntilMs = 0;
  snprintf(uiDebugText, sizeof(uiDebugText), "ENC IDLE");
  drawVolumeUi(currentVolume, currentModeText());
}

bool dialBackendReady() {
#if !ARDUINO_USB_MODE
  return HID.ready();
#elif defined(CONFIG_BLUEDROID_ENABLED)
  return bleDialConnected && bleMediaInputReport != nullptr;
#else
  return false;
#endif
}

void printUsbHidStatus(const char* reason) {
#if !ARDUINO_USB_MODE
  DIAL_SERIAL.printf(
      ">HID_STATUS reason=%s usb_mode=%s cdc_on_boot=%d control_channel=%s hid_supported=1 usb_started=%d hid_ready=%d dial_backend=%s dial_backend_ready=%d backend_status=%s ble_connected=0 ble_advertising=0 product=%s note=%s last_backend_error=none last_send_type=none\n",
      reason,
      DIAL_USB_MODE_NAME,
      ARDUINO_USB_CDC_ON_BOOT,
      DIAL_CONTROL_CHANNEL_NAME,
      usbStartedSeen ? 1 : 0,
      dialBackendReady() ? 1 : 0,
      dialBackendName(),
      dialBackendReady() ? 1 : 0,
      dialBackendStatus(),
      USB_PRODUCT_NAME,
      dialBackendNote());
#else
  DIAL_SERIAL.printf(
      ">HID_STATUS reason=%s usb_mode=%s cdc_on_boot=%d control_channel=%s hid_supported=0 usb_started=0 hid_ready=0 dial_backend=%s dial_backend_ready=%d backend_status=%s ble_connected=%d ble_advertising=%d product=%s note=%s last_backend_error=%s last_send_type=%s\n",
      reason,
      DIAL_USB_MODE_NAME,
      ARDUINO_USB_CDC_ON_BOOT,
      DIAL_CONTROL_CHANNEL_NAME,
      dialBackendName(),
      dialBackendReady() ? 1 : 0,
      dialBackendStatus(),
      bleDialConnected ? 1 : 0,
      bleDialAdvertisingActive ? 1 : 0,
      USB_PRODUCT_NAME,
      dialBackendNote(),
      bleLastBackendError,
      bleLastSendType);
#endif
}

#if !ARDUINO_USB_MODE
void onUsbEvent(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
  (void)arg;
  (void)event_base;
  arduino_usb_event_data_t* data = reinterpret_cast<arduino_usb_event_data_t*>(event_data);
  switch (event_id) {
    case ARDUINO_USB_STARTED_EVENT:
      usbStartedSeen = true;
      DIAL_SERIAL.println(">USB started");
      break;
    case ARDUINO_USB_STOPPED_EVENT:
      usbStartedSeen = false;
      usbHidReadySeen = false;
      DIAL_SERIAL.println(">USB stopped");
      break;
    case ARDUINO_USB_SUSPEND_EVENT:
      DIAL_SERIAL.printf(">USB suspend remote_wakeup=%d\n", data ? (data->suspend.remote_wakeup_en ? 1 : 0) : -1);
      break;
    case ARDUINO_USB_RESUME_EVENT:
      DIAL_SERIAL.println(">USB resume");
      break;
    default:
      DIAL_SERIAL.printf(">USB event=%ld\n", static_cast<long>(event_id));
      break;
  }
}

void onHidEvent(void* arg, esp_event_base_t event_base, int32_t event_id, void* event_data) {
  (void)arg;
  (void)event_base;
  arduino_usb_hid_event_data_t* data = reinterpret_cast<arduino_usb_hid_event_data_t*>(event_data);
  switch (event_id) {
    case ARDUINO_USB_HID_SET_PROTOCOL_EVENT:
      DIAL_SERIAL.printf(">HID set_protocol instance=%u protocol=%u\n",
                         data ? data->instance : 0,
                         data ? data->set_protocol.protocol : 0);
      break;
    case ARDUINO_USB_HID_SET_IDLE_EVENT:
      DIAL_SERIAL.printf(">HID set_idle instance=%u rate=%u\n",
                         data ? data->instance : 0,
                         data ? data->set_idle.idle_rate : 0);
      break;
    default:
      DIAL_SERIAL.printf(">HID event=%ld\n", static_cast<long>(event_id));
      break;
  }
}
#endif

void beginDialBackend() {
#if !ARDUINO_USB_MODE
  USB.productName(USB_PRODUCT_NAME);
  USB.manufacturerName(USB_MANUFACTURER_NAME);
  USB.firmwareVersion(USB_FW_VERSION_BCD);
  USB.onEvent(onUsbEvent);
  HID.onEvent(onHidEvent);
  dialHid.begin();
  USB.begin();
#elif defined(CONFIG_BLUEDROID_ENABLED)
  bleDialBackendBegun = true;
  setBleDialState(BleDialState::Initializing);
  setBleLastBackendError("none");
  logBleEvent("init");
  DIAL_SERIAL.println("[BLE-HID] init start");

  BLEDevice::init(USB_PRODUCT_NAME);

  // --- Task A: Bonded Just Works security ---
  {
    BLESecurity* bleSecurity = new BLESecurity();
#if defined(ESP_LE_AUTH_REQ_SC_BOND)
    bleSecurity->setAuthenticationMode(ESP_LE_AUTH_REQ_SC_BOND);
#else
    bleSecurity->setAuthenticationMode(ESP_LE_AUTH_BOND);
#endif
    bleSecurity->setCapability(ESP_IO_CAP_NONE);
    bleSecurity->setInitEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
    bleSecurity->setRespEncryptionKey(ESP_BLE_ENC_KEY_MASK | ESP_BLE_ID_KEY_MASK);
    bleSecurity->setKeySize(16);
  }
#if BLE_FORCE_ENCRYPTION_LEVEL
  BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT);
  DIAL_SERIAL.println("[BLE-HID] security: SC_BOND + IO_NONE + ENC");
#else
  DIAL_SERIAL.println("[BLE-HID] security: SC_BOND + IO_NONE");
  DIAL_SERIAL.println("[BLE-HID] force encryption level: disabled");
#endif

  // --- Task B: stable random static address ---
  fillBleDialRandomAddress(bleDialRandomAddress);
  {
    char buf[48];
    snprintf(buf, sizeof(buf), "[BLE-HID] address: %02X:%02X:%02X:%02X:%02X:%02X",
             bleDialRandomAddress[0], bleDialRandomAddress[1], bleDialRandomAddress[2],
             bleDialRandomAddress[3], bleDialRandomAddress[4], bleDialRandomAddress[5]);
    DIAL_SERIAL.println(buf);
  }

  // --- HID device setup ---
  DIAL_SERIAL.printf("[BLE-HID] media report id: %u\n", MEDIA_REPORT_ID);
  bleDialServer = BLEDevice::createServer();
  bleDialServer->setCallbacks(new DialBleServerCallbacks());
  bleDialHid = new BLEHIDDevice(bleDialServer);

  uint16_t descLen = 0;
  const uint8_t* desc = getDialReportDescriptor(descLen);
  bleDialHid->reportMap(const_cast<uint8_t*>(desc), descLen);
  DIAL_SERIAL.printf("[BLE-HID] report map size: %u\n", descLen);

  // Consumer Control volume test: use MEDIA_REPORT_ID.
  bleMediaInputReport = bleDialHid->inputReport(MEDIA_REPORT_ID);
  DIAL_SERIAL.println("[BLE-HID] media input report created");

  // --- Task E: patch descriptor permissions on media report ---
  {
    BLEDescriptor* rptRef = bleMediaInputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2908));
    BLEDescriptor* cccd   = bleMediaInputReport->getDescriptorByUUID(BLEUUID((uint16_t)0x2902));
    if (rptRef) rptRef->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
    if (cccd)   cccd->setAccessPermissions(ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE);
    DIAL_SERIAL.printf("[BLE-HID] media descriptor permissions patched: 2908=%s, 2902=%s\n",
                       rptRef ? "yes" : "no", cccd ? "yes" : "no");
    if (rptRef) {
      // Report Reference value is set by the library: {reportID, 0x01}.
      // Should be {0x02, 0x01} for MEDIA_REPORT_ID=2.
      uint8_t* refVal = rptRef->getValue();
      size_t refLen = rptRef->getLength();
      if (refVal && refLen >= 2) {
        DIAL_SERIAL.printf("[BLE-HID] media report ref: %02X %02X\n", refVal[0], refVal[1]);
      } else {
        DIAL_SERIAL.printf("[BLE-HID] media report ref: missing or too short (len=%u)\n", refLen);
      }
    }
  }

  // TEST BRANCH: only MEDIA_REPORT_ID=2. No DIAL_REPORT_ID=1 secondary report.

  // --- Task F: Device Information Service ---
  bleDialHid->manufacturer();
  bleDialHid->manufacturer(USB_MANUFACTURER_NAME);
  bleDialHid->pnp(BLE_PNP_SIG, BLE_PNP_VID, BLE_PNP_PID, USB_FW_VERSION_BCD);
  bleDialHid->hidInfo(BLE_HID_COUNTRY, BLE_HID_FLAGS);

  bleDialHid->startServices();
  DIAL_SERIAL.println("[BLE-HID] services started");

  bleDialHid->setBatteryLevel(100);

  // --- Task C: 3-service 16-bit advertising ---
  bleDialAdvertising = bleDialServer->getAdvertising();
  {
    BLEAdvertisementData bleAdvData;
    BLEAdvertisementData bleScanData;

    bleAdvData.setFlags(ESP_BLE_ADV_FLAG_GEN_DISC | ESP_BLE_ADV_FLAG_BREDR_NOT_SPT);

    // Appearance: Generic HID = 0x03C0 (little-endian: C0 03)
    {
      uint8_t appearanceAD[] = {0x03, 0x19, 0xC0, 0x03};
      bleAdvData.addData(std::string(reinterpret_cast<char*>(appearanceAD), sizeof(appearanceAD)));
    }

    // Complete List of 16-bit Service UUIDs: HID, Battery, Device Information
    {
      uint8_t svcAD[] = {0x07, 0x03, 0x12, 0x18, 0x0F, 0x18, 0x0A, 0x18};
      bleAdvData.addData(std::string(reinterpret_cast<char*>(svcAD), sizeof(svcAD)));
    }

    // Name in scan response to keep primary AD under 31 bytes
    bleScanData.setName(USB_PRODUCT_NAME);

    bleDialAdvertising->setAdvertisementData(bleAdvData);
    bleDialAdvertising->setScanResponseData(bleScanData);
  }
  DIAL_SERIAL.println("[BLE-HID] adv services: 1812,180F,180A");

  bleDialAdvertising->setScanResponse(true);
  bleDialAdvertising->setMinPreferred(0x06);
  bleDialAdvertising->setMaxPreferred(0x12);
  bleDialAdvertising->setDeviceAddress(bleDialRandomAddress, BLE_ADDR_TYPE_RANDOM);
  bleDialServer->startAdvertising();
  DIAL_SERIAL.println("[BLE-HID] advertising started");

  bleDialAdvertisingActive = true;
  setBleDialState(BleDialState::Advertising);
  logBleEvent("advertising", "start");
  printUsbHidStatus("ble_advertising_start");
#else
  bleDialBackendBegun = true;
#endif
}

bool dialBackendSendRotate(int direction) {
#if !ARDUINO_USB_MODE
  if (!HID.ready()) return false;
  bool ok1 = dialHid.sendReport(0, direction > 0 ? DIAL_ROTATE_RIGHT : DIAL_ROTATE_LEFT);
  bool ok2 = dialHid.sendReport(0, 0);
  return ok1 && ok2;
#elif defined(CONFIG_BLUEDROID_ENABLED)
  int8_t delta = direction > 0 ? DIAL_ROTATE_RIGHT : DIAL_ROTATE_LEFT;
  setBleDialState(BleDialState::SendingRotate);
  DIAL_SERIAL.printf(">BLE report rotate delta=%d\n", delta);
  return bleDialSendReport(0, delta, direction > 0 ? "rotate_right" : "rotate_left");
#else
  (void)direction;
  return bleDialBackendBegun && dialBackendReady();
#endif
}

bool dialBackendSendPressPulse() {
#if !ARDUINO_USB_MODE
  if (!HID.ready()) return false;
  bool ok1 = dialHid.sendReport(DIAL_BUTTON_PRESS, 0);
  bool ok2 = dialHid.sendReport(0, 0);
  return ok1 && ok2;
#elif defined(CONFIG_BLUEDROID_ENABLED)
  setBleDialState(BleDialState::SendingPress);
  logBleEvent("report", "press");
  return bleDialSendReport(DIAL_BUTTON_PRESS, 0, "press");
#else
  return bleDialBackendBegun && dialBackendReady();
#endif
}

void emitVolume(int volume) {
  currentVolume = max(0, min(100, volume));
  DIAL_SERIAL.printf(">VOLUME %d\n", currentVolume);
  drawVolumeUi(currentVolume, currentModeText());
}

void dispatchRotateEvent(int direction, const char* source) {
  if (direction == 0) return;
  const char* dirText = direction > 0 ? "RIGHT" : "LEFT";
  setModeText("ENCODER");
  setDebugText(source, dirText, true);
  int nextVolume = currentVolume + (direction > 0 ? ENCODER_STEP : -ENCODER_STEP);
  nextVolume = max(0, min(100, nextVolume));
  bool sentHid = dialBackendSendRotate(direction);
  DIAL_SERIAL.printf(
      ">ENC source=%s dir=%s volume=%d hid=%s ready=%s backend=%s\n",
      source,
      dirText,
      nextVolume,
      sentHid ? "sent" : "skip",
      dialBackendReady() ? "yes" : "no",
      dialBackendName());
  emitVolume(nextVolume);
}

void dispatchPressPulseEvent(const char* source) {
  setModeText("ENCODER");
  setDebugText(source, "PRESS", true);
  bool sentHid = dialBackendSendPressPulse();
  DIAL_SERIAL.printf(
      ">ENC_PRESS source=%s hid=%s ready=%s backend=%s\n",
      source,
      sentHid ? "sent" : "skip",
      dialBackendReady() ? "yes" : "no",
      dialBackendName());
  DIAL_SERIAL.println(">PRESS");
  drawVolumeUi(currentVolume, currentModeText(), true);
}

void emitLegacyTouchAbsoluteVolume(int volume, uint16_t x, uint16_t y) {
  unsigned long now = millis();
  if (volume < 0) return;
  if (volume == lastSentVolume && now - lastVolumeSendMs < 500) return;
  if (now - lastVolumeSendMs < VOLUME_SEND_MIN_MS) return;

  lastVolumeSendMs = now;
  lastSentVolume = volume;
  currentVolume = volume;
  DIAL_SERIAL.printf(">TOUCH x=%u y=%u volume=%d\n", x, y, volume);
  emitVolume(volume);
  // Legacy MVP path: touch ring still emits absolute volume during transition.
}

void emitLegacyTouchLongPress() {
  setModeText("MUTE");
  setDebugText("TOUCH", "HOLD", true);
  DIAL_SERIAL.println(">MUTE_TOGGLE");
  sendMute();
  drawVolumeUi(currentVolume, currentModeText(), true);
}

void IRAM_ATTR onEncoderEdge() {
  sEncState = ((sEncState << 2) & 0x0F) | (digitalRead(PIN_ENC_CLK) << 1) | digitalRead(PIN_ENC_DT);
  int8_t delta = ENC_TABLE[sEncState];
  sEncDir += delta;
  if (sEncDir > 8) sEncDir = 8;
  if (sEncDir < -8) sEncDir = -8;
}

void handleEncoder() {
  int direction = 0;
  noInterrupts();
  if (sEncDir >= 4) {
    sEncDir -= 4;
    direction = 1;
  } else if (sEncDir <= -4) {
    sEncDir += 4;
    direction = -1;
  }
  interrupts();

  if (direction != 0) {
    dispatchRotateEvent(direction, "ENC");
  }

  bool swLow = digitalRead(PIN_ENC_SW) == LOW;
  if (swLow && !sEncSwitchWasLow) {
    encSwitchDownMs = millis();
    encLongPressSent = false;
  }
  if (swLow && !encLongPressSent && millis() - encSwitchDownMs >= LONG_PRESS_MS) {
    encLongPressSent = true;
    sendMute();
  }
  if (!swLow && sEncSwitchWasLow && !encLongPressSent) {
    // Short press: released before LONG_PRESS_MS.
    dispatchPressPulseEvent("ENC");
  }
  sEncSwitchWasLow = swLow;
}

void handleTouch() {
  if (!touchPresent) return;

  unsigned long now = millis();
  if (now - lastTouchPollMs < TOUCH_POLL_MS) return;
  lastTouchPollMs = now;

  TouchPoint tp;
  if (!readTouch(tp)) return;

  if (tp.touched) {
    if (!wasTouching) {
      wasTouching = true;
      centerCandidate = isCenter(tp.x, tp.y);
      longPressSent = false;
      touchDownMs = now;
      DIAL_SERIAL.printf(">TOUCH down x=%u y=%u\n", tp.x, tp.y);
    }

    if (centerCandidate) {
      if (!isCenter(tp.x, tp.y)) centerCandidate = false;
      if (!longPressSent && now - touchDownMs >= LONG_PRESS_MS) {
        longPressSent = true;
        emitLegacyTouchLongPress();
      }
    } else {
      int volume = pointToVolume(tp.x, tp.y);
      emitLegacyTouchAbsoluteVolume(volume, tp.x, tp.y);
    }
    return;
  }

  if (wasTouching) {
    unsigned long held = now - touchDownMs;
    if (centerCandidate && !longPressSent && held <= TAP_MAX_MS && now - lastPressMs >= PRESS_DEBOUNCE_MS) {
      lastPressMs = now;
      dispatchPressPulseEvent("TOUCH");
    }
    DIAL_SERIAL.println(">TOUCH up");
  }

  wasTouching = false;
  centerCandidate = false;
  longPressSent = false;
}

void enterWired() {
  if (wired) return;
  wired = true;
  lastAckMs = millis();
  lastPingMs = millis();
  setModeText("WIRED");
  DIAL_SERIAL.println(">MODE wired");
  drawVolumeUi(currentVolume, currentModeText(), true);
}

void enterWaitPc() {
  if (!wired) return;
  wired = false;
  setModeText("WAIT PC");
  drawVolumeUi(currentVolume, currentModeText(), true);
}

void handleLine(const char* line) {
  if (strcmp(line, "ACK") == 0) {
    lastAckMs = millis();
    enterWired();
    return;
  }
  if (strcmp(line, "ENC LEFT") == 0 || strcmp(line, "SIM LEFT") == 0) {
    dispatchRotateEvent(-1, "SIM");
    return;
  }
  if (strcmp(line, "ENC RIGHT") == 0 || strcmp(line, "SIM RIGHT") == 0) {
    dispatchRotateEvent(1, "SIM");
    return;
  }
  if (strcmp(line, "ENC PRESS") == 0 || strcmp(line, "SIM PRESS") == 0) {
    dispatchPressPulseEvent("SIM");
    return;
  }
  if (strcmp(line, "ENC STATUS") == 0) {
    DIAL_SERIAL.printf(">ENC_STATUS mode=%s debug=%s volume=%d hid=%s backend=%s backend_status=%s ble_connected=%d ble_advertising=%d last_send_type=%s\n",
                       currentModeText(),
                       uiDebugText,
                       currentVolume,
                       dialBackendReady() ? "ready" : "wait",
                       dialBackendName(),
                       dialBackendStatus(),
#if ARDUINO_USB_MODE && defined(CONFIG_BLUEDROID_ENABLED)
                       bleDialConnected ? 1 : 0,
                       bleDialAdvertisingActive ? 1 : 0,
                       bleLastSendType
#else
                       0,
                       0,
                       "none"
#endif
                       );
    return;
  }

  if (strcmp(line, "HID STATUS") == 0 || strcmp(line, "USB STATUS") == 0) {
    printUsbHidStatus("serial_cmd");
  }
}

void readSerialLines() {
  while (DIAL_SERIAL.available() > 0) {
    char c = static_cast<char>(DIAL_SERIAL.read());
    if (c == '\n' || c == '\r') {
      if (rxLen > 0) {
        rxLine[rxLen] = '\0';
        handleLine(rxLine);
        rxLen = 0;
      }
    } else if (rxLen < sizeof(rxLine) - 1) {
      rxLine[rxLen++] = c;
    } else {
      rxLen = 0;
    }
  }
}

}  // namespace

void setup() {
  DIAL_SERIAL.begin(115200);
  delay(20);
  probeLog("setup.begin");
  beginDialBackend();
  probeLog("after.hidBegin");
  delay(50);
  printUsbHidStatus("boot");
  probeLog("after.boot_status");

  pinMode(PIN_LCD_BL, OUTPUT);
  digitalWrite(PIN_LCD_BL, HIGH);
  pinMode(PIN_ENC_CLK, INPUT_PULLUP);
  pinMode(PIN_ENC_DT, INPUT_PULLUP);
  pinMode(PIN_ENC_SW, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_CLK), onEncoderEdge, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_DT), onEncoderEdge, CHANGE);
  probeLog("after.gpio_irq");
  delay(50);
  probeLog("before.tft.begin");
  tft.begin(1000000);
  probeLog("after.tft.begin");
  tft.setRotation(0);
  probeLog("after.tft.rotation");
  frame = new GFXcanvas16(240, 240);
  probeLog(frame == nullptr || frame->getBuffer() == nullptr ? "frame.alloc.fail" : "frame.alloc.ok");
  if (frame == nullptr || frame->getBuffer() == nullptr) {
    DIAL_SERIAL.println(">ERR framebuffer_alloc_failed");
    while (true) delay(1000);
  }
  setModeText("BOOT");
  probeLog("before.draw.boot_ui");
  drawVolumeUi(currentVolume, currentModeText(), true);
  probeLog("after.draw.boot_ui");

  probeLog("before.wire.begin");
  Wire.begin(PIN_TP_SDA, PIN_TP_SCL, 100000);
  probeLog("after.wire.begin");
  resetTouch();
  probeLog("after.resetTouch");

  delay(500);
  DIAL_SERIAL.println();
  DIAL_SERIAL.println(">BOOT esp32s3_touch_dial touch_mvp");
  probeLog("before.scanI2C");
  scanI2C();
  probeLog("after.scanI2C");
  touchPresent = probeTouch();
  probeLog(touchPresent ? "probeTouch.present" : "probeTouch.absent");
  dumpTouchRegs("boot");
  probeLog("after.dumpTouchRegs");
  if (!bootModeSent) {
    DIAL_SERIAL.println(">MODE boot");
    bootModeSent = true;
  }
  setModeText(touchPresent ? "WAIT PC" : "NO TOUCH");
  probeLog("before.draw.final_ui");
  drawVolumeUi(currentVolume, currentModeText(), true);
  probeLog("setup.done");
}

void loop() {
  static unsigned long lastLoopProbeMs = 0;
  unsigned long now = millis();
  if (now - lastLoopProbeMs >= 3000) {
    lastLoopProbeMs = now;
    probeLog(wired ? "loop.wired" : "loop.wait_pc");
  }
  if (usbHidReadySeen && !dialBackendReady()) {
    usbHidReadySeen = false;
  }
  if (!usbHidReadySeen && dialBackendReady()) {
    usbHidReadySeen = true;
    DIAL_SERIAL.println(">HID ready");
    printUsbHidStatus("ready_edge");
  }
  readSerialLines();
  handleEncoder();
  handleTouch();
  refreshIdleDebugIfNeeded();

  if (!wired) {
    if (now - lastHelloMs >= HELLO_INTERVAL_MS) {
      lastHelloMs = now;
      DIAL_SERIAL.println(">HELLO");
    }
    return;
  }

  if (now - lastAckMs >= ACK_TIMEOUT_MS) {
    enterWaitPc();
    return;
  }

  if (now - lastPingMs >= PING_INTERVAL_MS) {
    lastPingMs = now;
    DIAL_SERIAL.println(">PING");
  }
}

