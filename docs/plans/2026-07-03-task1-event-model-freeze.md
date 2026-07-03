# Task 1 — Unified Dial Event Model Freeze

> Status: frozen baseline for follow-up implementation

**Purpose:** Freeze a single internal event model for the current `esp32s3_touch_dial` firmware so that encoder, touch, CDC debug, and HID output all converge on the same semantics. This document is the contract for future implementation work.

---

## 1. What we learned from the current code

Current firmware behavior in `esp32s3_touch_dial.ino` splits into two different semantic families:

### Family A: Dial-like semantics (good, should become primary)
Used by encoder path:
- `applyEncoderStep(direction, source)`
- `emitEncoderPress(source)`
- `hidSendRotate(direction)`
- `hidSendPressPulse()`

Characteristics:
- relative rotate left/right
- press pulse
- optional HID output
- screen feedback already updates around encoder activity

### Family B: Legacy MVP serial semantics (temporary compatibility only)
Used by touch path:
- `maybeEmitVolumeFromTouch(volume, x, y)`
- center short tap -> `>PRESS`
- center long press -> `>MUTE_TOGGLE`
- ring touch -> direct absolute `>VOLUME N`

Characteristics:
- absolute volume target
- app-specific action names
- tied to serial MVP protocol
- not Surface Dial-like

Conclusion:
- Encoder path is already close to the target product semantics.
- Touch path still reflects the old “touch volume ring MVP” design and must stop defining the product architecture.

---

## 2. Frozen internal event model

From this point onward, the firmware should treat the following as the canonical internal event layer.

### 2.1 Core events

1. `rotate_left(step=1)`
2. `rotate_right(step=1)`
3. `press_pulse()`

These three are the minimum product events and must be supported by the encoder path first.

### 2.2 Optional extended events

4. `press_hold_start()`
5. `press_hold_end()`
6. `mode_change(mode_id)`
7. `source_activity(source_id, detail)`

These are secondary support events for UI state, touch-assisted UX, or future richer HID behavior.

### 2.3 Explicit non-core events

The following are NOT canonical product events anymore:
- `set_absolute_volume(n)`
- `mute_toggle()`
- raw `>TOUCH down/up`
- raw `>VOLUME N`
- raw `>PRESS`
- raw `>MUTE_TOGGLE`

These may continue to exist temporarily as:
- debug/compatibility outputs
- adapter outputs generated from the canonical event layer
- transition artifacts while migrating old tools

But they must no longer drive the architecture.

---

## 3. Source-to-event mapping

### 3.1 Encoder mapping (primary input source)

Frozen mapping:
- encoder detent left -> `rotate_left(1)`
- encoder detent right -> `rotate_right(1)`
- encoder switch press edge -> `press_pulse()`

Notes:
- This is now the primary product interaction path.
- If a future conflict exists between touch and encoder, encoder semantics win.

### 3.2 Touch mapping (secondary / assistive input source)

Frozen interim mapping:
- center short tap -> temporary adapter to `press_pulse()`
- center long press -> reserved for UI mode behavior, not frozen as product-level `mute_toggle()`
- outer ring absolute volume -> legacy compatibility only, scheduled for de-primarying

Future intent:
- touch should evolve toward menu/navigation/selection/auxiliary actions
- touch should not remain a second full-strength primary Dial input path

### 3.3 Serial simulation mapping

Current commands such as:
- `ENC LEFT`
- `ENC RIGHT`
- `ENC PRESS`
- `SIM LEFT`
- `SIM RIGHT`
- `SIM PRESS`

should be treated as debug adapters that inject the same canonical events:
- `rotate_left(1)`
- `rotate_right(1)`
- `press_pulse()`

---

## 4. Output/backend mapping

The event layer must be backend-agnostic.

### 4.1 HID backend (target primary backend)

Canonical event mapping:
- `rotate_left/right` -> HID dial relative delta
- `press_pulse()` -> HID button pulse

This backend is the target product path.

### 4.2 CDC debug backend (keep, but demote)

Current text outputs remain useful, but are now classified as debug/compatibility:
- `>ENC ...`
- `>ENC_PRESS ...`
- `>HID_STATUS ...`
- `>MODE ...`
- `>BOOT ...`

Legacy outputs such as `>VOLUME N`, `>PRESS`, `>MUTE_TOGGLE` may survive for transition, but must be considered adapter outputs, not architecture drivers.

### 4.3 Screen/UI backend

The screen should render state derived from canonical events, not define them.

Preferred UI responsibilities:
- current mode
- recent input source
- recent rotate direction
- press feedback
- optional menu/selection status

The screen is a presentation layer, not the primary input contract.

---

## 5. Frozen product decision

### Decision
Adopt “A as primary, B as assistive”:
- encoder = primary input
- screen = primary feedback
- touch = secondary assistive input

### Rejected direction for now
Do not make touch + encoder two completely symmetric independent Dial-capable primary inputs.

Reason:
- worse alignment with Surface Dial target
- significantly higher implementation complexity
- makes HID validation and UX convergence harder

---

## 6. Required code boundaries for the next implementation step

The next implementation step should introduce a clearer event boundary in code.

### Recommended boundary
Create or emulate a layer conceptually equivalent to:

- `dispatchRotate(direction, source)`
- `dispatchPressPulse(source)`
- optional `dispatchHold(source)`

Current likely consolidation points in `esp32s3_touch_dial.ino`:
- `applyEncoderStep(...)`
- `emitEncoderPress(...)`
- touch short tap path in `handleTouch()`
- touch long press path in `handleTouch()`
- serial simulation path in `handleLine()`

### What should happen next
1. Move business meaning to the dispatch layer
2. Treat HID, serial text, and screen refresh as backends reacting to events
3. Keep old serial outputs only as compatibility adapters until Windows HID-only validation is complete

---

## 7. Immediate implementation implications

From this freeze onward:
- new feature work should be written against rotate/press semantics first
- no new product behavior should be introduced primarily through `>VOLUME N`
- touch ring absolute volume logic should be treated as legacy MVP behavior pending redesign
- HID-only Windows validation is now the next most important gate

---

## 8. Acceptance criteria for Task 1

Task 1 is complete when:
- there is a written frozen event contract
- encoder is explicitly recognized as the product’s primary event source
- touch absolute volume is explicitly demoted to legacy/transition status
- future tasks can implement against this contract without re-deciding product semantics

Status: complete.
