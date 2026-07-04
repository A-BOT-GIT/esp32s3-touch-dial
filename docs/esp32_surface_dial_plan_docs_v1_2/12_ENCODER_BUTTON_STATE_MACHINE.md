# 12 编码器与按钮状态机设计

版本：v1.2

## 1. 目标

Surface Dial 语义中：

```text
按钮 = Windows RadialController 菜单 / 点击 / 按住
旋钮 = 当前菜单项或 app action 的连续变化
```

因此固件不应该自行把短按映射为 Play/Pause，也不应该把长按映射为 Mute。

---

## 2. 状态变量

建议：

```cpp
static bool radialButtonPressed = false;
static bool radialButtonLongPressLogged = false;
static uint32_t radialButtonDownMs = 0;

static int32_t encoderLastPosition = 0;
static uint32_t lastEncoderReportMs = 0;
```

---

## 3. 按键状态机

```text
IDLE
  button down -> PRESSED
PRESSED
  rotate -> sendRadialReport(true, delta)
  hold timeout -> HOLDING_LOGGED
  button up -> IDLE
HOLDING_LOGGED
  rotate -> sendRadialReport(true, delta)
  button up -> IDLE
```

注意：HOLDING_LOGGED 不发送特殊 HID usage，只打印诊断。

---

## 4. 按下事件

```cpp
void handleButtonDown() {
  if (radialButtonPressed) {
    return;
  }

  radialButtonPressed = true;
  radialButtonLongPressLogged = false;
  radialButtonDownMs = millis();

  bool ok = sendRadialReport(true, 0);

  Serial.printf(">ENC_BUTTON down hid=%s\n", ok ? "sent" : "skip");
}
```

---

## 5. 释放事件

```cpp
void handleButtonUp() {
  if (!radialButtonPressed) {
    return;
  }

  uint32_t heldMs = millis() - radialButtonDownMs;

  radialButtonPressed = false;
  radialButtonLongPressLogged = false;

  bool ok = sendRadialReport(false, 0);

  Serial.printf(">ENC_BUTTON up held_ms=%lu hid=%s\n",
                (unsigned long)heldMs,
                ok ? "sent" : "skip");
}
```

---

## 6. 长按检测

```cpp
void pollButtonHold() {
  if (!radialButtonPressed) {
    return;
  }

  if (!radialButtonLongPressLogged && millis() - radialButtonDownMs >= 800) {
    radialButtonLongPressLogged = true;
    Serial.println(">ENC_BUTTON hold candidate for radial menu");
  }
}
```

不要在这里发：

```cpp
sendMute();
sendPlayPause();
```

Windows 需要看到的是 button 持续为 1，然后自行决定是否打开 radial menu。

---

## 7. 旋转事件

```cpp
void handleEncoderDelta(int deltaSteps) {
  if (deltaSteps == 0) {
    return;
  }

  int16_t radialDelta = deltaSteps > 0
      ? RADIAL_DELTA_UNIT
      : -RADIAL_DELTA_UNIT;

  bool ok = sendRadialReport(radialButtonPressed, radialDelta);

  Serial.printf(">ENC rotate dir=%s button=%d radial_delta=%d hid=%s\n",
                deltaSteps > 0 ? "RIGHT" : "LEFT",
                radialButtonPressed ? 1 : 0,
                radialDelta,
                ok ? "sent" : "skip");
}
```

---

## 8. 旋钮节流

如果编码器一格触发很多脉冲，可以做简单节流：

```cpp
#ifndef RADIAL_MIN_REPORT_INTERVAL_MS
#define RADIAL_MIN_REPORT_INTERVAL_MS 10
#endif

bool canSendEncoderReport() {
  uint32_t now = millis();
  if (now - lastEncoderReportMs < RADIAL_MIN_REPORT_INTERVAL_MS) {
    return false;
  }
  lastEncoderReportMs = now;
  return true;
}
```

MVP 初期可以先不启用节流，避免丢事件。若 Windows 反应过快，再加。

---

## 9. delta 单位调试

初始：

```cpp
#define RADIAL_DELTA_UNIT 1
```

如果 Windows / Probe 显示旋转太慢：

```cpp
#define RADIAL_DELTA_UNIT 10
```

每次调整单位都要记录：

```text
identity
RADIAL_DELTA_UNIT
Probe delta 表现
```

---

## 10. 消抖

按键消抖建议：

```cpp
#ifndef BUTTON_DEBOUNCE_MS
#define BUTTON_DEBOUNCE_MS 30
#endif
```

逻辑：

```cpp
if (millis() - lastButtonEdgeMs < BUTTON_DEBOUNCE_MS) {
  ignore;
}
```

编码器消抖按现有库/中断逻辑保留，不在 Radial MVP 首轮大改。

---

## 11. 实测用例

### 用例 A：短按

预期：

```text
button down -> 01 00
button up   -> 00 00
```

### 用例 B：长按

预期：

```text
button down -> 01 00
hold log
button up   -> 00 00
```

### 用例 C：按住旋转

预期：

```text
button down -> 01 00
rotate right while button=1 -> 03 00
rotate left while button=1  -> FF FF
button up -> 00 00
```

### 用例 D：普通旋转

预期：

```text
right -> 02 00
left  -> FE FF
```
