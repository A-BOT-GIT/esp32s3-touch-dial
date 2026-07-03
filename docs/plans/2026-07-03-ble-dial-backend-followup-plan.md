# BLE Dial Backend Follow-up Implementation Plan

> **For Hermes:** Continue implementation inside `/home/zza/projects/esp32s3_touch_dial` only. After each meaningful increment, run `rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q` and both compile targets:
> - `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial`
> - `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial`

**Goal:** Evolve the current BLE Dial backend from a compile-safe advertise/connect skeleton into a Windows-verifiable, observable, and maintainable BLE HID dial path without regressing the existing USB TinyUSB HID backend.

**Architecture:** Keep the existing event-model freeze intact: encoder/touch input continues to emit backend-agnostic rotate/press events, while backend-specific send paths stay behind the dial backend abstraction. Advance BLE in layers: first observability, then send semantics, then Windows validation, then HID compatibility tuning, and finally codebase cleanup.

**Tech Stack:** Arduino ESP32 core 2.0.17, ESP32 BLE Arduino (`BLEDevice`, `BLEServer`, `BLEHIDDevice`), pytest, arduino-cli, existing HID capture analysis tooling.

---

## Current Baseline

Already complete:
- Git/GitHub and GitHub Actions are configured.
- `pytest` is green.
- Both compile targets are green.
- USB TinyUSB backend remains the reference implementation.
- BLE backend now performs real init / HID service creation / advertising / connect-disconnect state transitions.
- HID status logs already expose `dial_backend`, `dial_backend_ready`, `backend_status`, and `note`.
- BLE HID init crash caused by calling `manufacturer(name)` before creating the optional manufacturer characteristic has been fixed.
- Linux-side bring-up is now empirically verified: after conservative flashing the board reaches `>BLE advertising start` instead of rebooting at `>BLE init`.

Current gaps:
- BLE observability is still too coarse for reliable debugging.
- BLE send semantics are still a minimal notify skeleton.
- Windows host consumption of BLE reports is not yet proven.
- Descriptor/appearance/report compatibility may still need tuning.
- BLE-specific implementation is still concentrated in `esp32s3_touch_dial.ino`.
- `arduino-cli upload` is not yet a trustworthy success signal on this board's native USB path; flashing guidance should explicitly prefer runtime serial verification and keep a manual `esptool.py` fallback documented.

---

## Phase A: Observability Hardening

**Objective:** Make BLE state transitions and send decisions visible from both firmware serial logs and the Python HID capture analysis tools.

### Task A1: Introduce explicit BLE backend state tracking

**Objective:** Replace implicit BLE status inference with an explicit backend state variable.

**Files:**
- Modify: `esp32s3_touch_dial.ino`

**Implementation details:**
- Add a compact BLE state enum or equivalent constants for:
  - `uninitialized`
  - `initializing`
  - `advertising`
  - `connected_idle`
  - `sending_rotate`
  - `sending_press`
  - `restarting_advertising`
  - `error`
- Add backing fields such as:
  - `bleDialState`
  - `bleLastBackendError`
  - `bleLastSendType`
  - `bleLastSendMs`
- Make `dialBackendStatus()` derive from the explicit state rather than mostly from pointer/boolean combinations.

**Verification:**
- Build both compile targets.
- Confirm `HID_STATUS` transitions through explicit states during boot, connect, disconnect, and send attempts.

### Task A2: Extend HID status fields with BLE-specific observability

**Objective:** Expose enough machine-readable fields for downstream tooling to explain BLE behavior without guessing.

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Modify: `tools/analyze_hid_captures.py`
- Modify: `tests/test_hid_capture_analysis.py`

**Fields to add:**
- `ble_connected=0/1`
- `ble_advertising=0/1`
- `last_backend_error=...`
- `last_send_type=...`

**Implementation details:**
- Append these fields to `printUsbHidStatus()`.
- Add the same high-value subset to `ENC STATUS` for manual serial diagnostics.
- Extend the parser in `tools/analyze_hid_captures.py`.
- Add/extend tests so capture analysis reports include the new fields.

**Verification:**
- First write a failing pytest for a BLE advertising sample.
- Then implement parsing and report rendering.
- Re-run full pytest and both compile targets.

### Task A3: Add structured BLE event logs

**Objective:** Make event flow visible even when the host never consumes reports.

**Files:**
- Modify: `esp32s3_touch_dial.ino`

**Logs to emit:**
- `>BLE init`
- `>BLE advertising start`
- `>BLE advertising restart`
- `>BLE connected`
- `>BLE disconnected`
- `>BLE report rotate delta=...`
- `>BLE report press`
- `>BLE report skip reason=...`

**Implementation details:**
- Add a small helper to avoid duplicated log formatting.
- For skipped sends, report why (`not_ready`, `report_missing`, etc.).
- Keep output terse so serial capture remains parseable.

**Verification:**
- Compile both targets.
- On manual serial inspection, confirm boot → advertising → connected → disconnected transitions are visible.

---

## Phase B: BLE Send Semantics Stabilization

**Objective:** Make rotate/press report emission predictable and easier to tune.

### Task B1: Centralize BLE report emission helpers

**Files:**
- Modify: `esp32s3_touch_dial.ino`

**Implementation details:**
- Add helpers such as:
  - `bool bleDialSendReport(uint8_t buttons, int8_t delta, const char* send_type)`
  - `bool bleDialSendReleaseReport()`
- Move duplicated `setValue()` / `notify()` / release-report logic out of backend send functions.

**Verification:**
- Run pytest and both compile targets.
- Confirm rotate/press paths still compile and log expected send types.

### Task B2: Add send-rate controls

**Files:**
- Modify: `esp32s3_touch_dial.ino`

**Implementation details:**
- Add BLE-specific minimum interval constants for rotate and press sends.
- Gate high-frequency sends using `millis()`.
- Optionally accumulate or coalesce rapid rotate detents if host behavior requires it.

**Verification:**
- Compile both targets.
- Manual serial simulation should show skipped sends when rate-limited.

### Task B3: Separate link-ready from host-consumption confidence

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Modify: docs under `docs/plans/`

**Implementation details:**
- Keep `dial_backend_ready` defined as link-ready for now.
- Add internal notes or follow-up fields to differentiate:
  - link connected
  - notify path available
  - host consumption externally verified

**Verification:**
- Document exact meaning in validation notes to avoid false assumptions.

---

## Phase C: Windows BLE Validation Loop

**Objective:** Prove whether Windows can discover, pair, reconnect, and consume the BLE backend.

### Task C1: Write a BLE validation matrix document

**Files:**
- Create: `docs/plans/2026-07-03-ble-dial-validation-matrix.md`

**Include:**
- discovery
- pairing
- ready transition
- rotate behavior
- press behavior
- disconnect/re-advertise
- reconnect
- repeated input
- sleep/wake retest

### Task C2: Execute the matrix and record outcomes

**Files:**
- Update: `docs/plans/2026-07-03-ble-dial-validation-matrix.md`

**Implementation details:**
- Record serial observations, host behavior, and any HID capture artifacts.
- Explicitly classify each run as:
  - link only
  - partial HID
  - working input path
  - needs descriptor tuning

---

## Phase D: BLE HID Compatibility Tuning

**Objective:** If Windows can connect but not consume correctly, tune the identity and report details deliberately.

### Task D1: Isolate BLE HID identity constants

**Files:**
- Modify: `esp32s3_touch_dial.ino` or extracted backend files

**Implementation details:**
- Group these into one obvious configuration block:
  - appearance
  - PnP values
  - HID info flags
  - product/manufacturer text
  - report ID choices

### Task D2: Iterate on descriptor/report structure one variable at a time

**Files:**
- Modify: `esp32s3_touch_dial.ino`
- Update: validation matrix doc

**Implementation details:**
- Only change one of the following per experiment:
  - top-level usage
  - collection layout
  - button/delta layout
  - report IDs
- Record outcome after each iteration.

### Task D3: Compare behavior against the known working USB path

**Files:**
- Use current firmware and docs

**Implementation details:**
- Treat USB TinyUSB as the behavioral reference for rotate/press semantics.
- Keep BLE compatibility experiments isolated from USB behavior.

---

## Phase E: Code Structure Cleanup

**Objective:** Reduce backend complexity in the monolithic `.ino` and make future changes safer.

### Task E1: Extract backend-specific code

**Files:**
- Create/Modify candidates:
  - `src/dial_backend_common.h`
  - `src/usb_dial_backend.h/.cpp`
  - `src/ble_dial_backend.h/.cpp`
  - or Arduino-compatible header include splits if `.cpp` migration is too disruptive

**Implementation details:**
- Move shared report constants and helpers to common code.
- Move USB-only and BLE-only code into separate sections/files.

### Task E2: Add a status snapshot structure

**Implementation details:**
- Introduce a struct carrying the machine-readable backend status fields.
- Make status rendering consume the snapshot instead of scattered globals.

### Task E3: Extract report builders

**Implementation details:**
- Add clear helpers for rotate / press / release report byte generation.
- This enables simpler future reasoning and possible host-side mirror tests.

---

## Phase F: Product Experience and Documentation

**Objective:** Improve operator feedback and leave the repo in a reusable state.

### Task F1: Surface backend state on-screen

**Files:**
- Modify: `esp32s3_touch_dial.ino`

**Implementation details:**
- Display backend type and concise BLE state such as `ADV`, `CONN`, `WAIT`.
- Keep the UI secondary to the encoder interaction display.

### Task F2: Update README and validation docs

**Files:**
- Modify: `README.md`
- Modify/Create: docs under `docs/plans/`

**Implementation details:**
- Document USB vs BLE routes.
- Document exact build/validation commands.
- Document current known limitations.

---

## Testing Strategy

### Automated tests
- Primary suite:
  - `rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q`
- Focused test during TDD:
  - targeted `pytest` invocation for the specific new behavior first

### Compile verification
Run both after every meaningful firmware change:
- `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial`
- `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial`

### Manual validation inventory
- Serial logs for BLE boot/advertise/connect/disconnect/send/skip
- Windows discovery and pairing behavior
- Windows input behavior for rotate and press
- reconnect behavior after disconnect and reboot

### Coverage matrix
- `tools/analyze_hid_captures.py`
  - tested by `tests/test_hid_capture_analysis.py`
  - should cover BLE advertising, BLE ready, and future BLE-specific fields
- `esp32s3_touch_dial.ino`
  - compile-verified through both affected profiles
  - manually validated through serial logs and host interaction

---

## Execution Order

1. Phase A: observability hardening
2. Phase B: send semantics stabilization
3. Phase C: Windows validation loop
4. Phase D: HID compatibility tuning
5. Phase E: code structure cleanup
6. Phase F: product experience and documentation

---

## Immediate Next Work

Start now with Phase A:
1. Add a failing analysis test for BLE advertising-state fields.
2. Extend analysis parsing/reporting for the new fields.
3. Extend firmware status output and BLE event logs.
4. Run `pytest` and both compile targets before moving on.
