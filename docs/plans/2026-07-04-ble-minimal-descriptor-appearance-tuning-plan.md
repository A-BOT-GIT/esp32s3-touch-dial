# BLE Minimal Descriptor / Appearance Tuning Plan

> **For Hermes:** Continue implementation inside `/home/zza/projects/esp32s3_touch_dial` only. Keep changes minimal and reversible. After each meaningful increment, run:
> - `rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q`
> - `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial`
> - `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial`
>
> Do not refactor unrelated code. Do not change input event semantics. Prefer one identity/descriptor adjustment per validation round so Windows behavior changes remain attributable.

**Goal:** On the current BLE Dial path, make the smallest possible descriptor/appearance identity adjustments needed to improve Windows pairing/acceptance/consumption, while preserving the already-proven event flow and avoiding regressions to the existing USB path.

**Architecture:** Keep the current backend abstraction and event model frozen: encoder/touch still emit rotate/press events, and only the BLE HID identity layer is tuned. Work from outer identity inward: advertisement appearance and device identity first, then top-level HID usage/collection shape, then only if necessary PnP/HID info compatibility details. Each round must be validated with both local regression checks and one Windows capture.

**Tech Stack:** Arduino ESP32 core 2.0.17, ESP32 BLE Arduino (`BLEDevice`, `BLEServer`, `BLEHIDDevice`), pytest, arduino-cli, existing HID capture tooling, Windows BLE Settings validation.

---

## Current Evidence Baseline

Already proven from recent captures:
- Native USB CDC capture path is correct (`COM15` / `native_usb_hwcdc`).
- BLE advertising works.
- Windows attempts to connect.
- BLE backend can enter `connected_idle` and `dial_backend_ready=1`.
- Firmware can emit real BLE input sends:
  - `>BLE report rotate delta=...`
  - `>BLE report press`
  - `hid=sent ready=yes backend=ble_hid_dial`
- Windows Settings may still show `点击连接 -> 正在连接 -> 请尝试重新连接设备`.

Interpretation:
- Transport/event path is no longer the primary unknown.
- The highest-value next step is tuning BLE HID identity compatibility with minimal surface area.

---

## Non-Goals

Do not do these in this plan:
- No large firmware refactor.
- No changes to encoder scanning logic.
- No new host-side helper app.
- No broad retry/reconnect redesign.
- No switching away from BLE to a different product strategy.
- No speculative changes to multiple identity layers at once.

---

## Files in Scope

Primary firmware file:
- Modify: `/home/zza/projects/esp32s3_touch_dial/esp32s3_touch_dial.ino`

Regression tooling:
- Modify only if needed: `/home/zza/projects/esp32s3_touch_dial/tests/test_hid_capture_analysis.py`
- Modify only if needed: `/home/zza/projects/esp32s3_touch_dial/tools/analyze_hid_captures.py`

Planning / notes:
- This plan: `/home/zza/projects/esp32s3_touch_dial/docs/plans/2026-07-04-ble-minimal-descriptor-appearance-tuning-plan.md`

---

## Working Hypotheses To Test In Order

### H1: Advertising appearance is too generic
Current code advertises:
- `bleAdvData.setAppearance(GENERIC_HID);`

Hypothesis:
- Windows may connect inconsistently or classify the device poorly because appearance is too generic for a dial-style HID identity.

### H2: Top-level HID usage/collection shape is not what Windows expects for stable dial-like behavior
Current report descriptor starts with:
- Usage Page (Generic Desktop)
- Usage (System Multi-Axis Controller)
- child Usage (Dial)

Hypothesis:
- Windows may accept the connection, but not treat the device as a compatible radial/dial-style input endpoint.

### H3: BLE HID identity metadata (PnP/HID info/name) is insufficiently aligned
Current code uses:
- `pnp(0x02, 0x303A, 0x1001, USB_FW_VERSION_BCD)`
- `hidInfo(0x00, 0x01)`
- product name = `ESP32-S3 Touch Dial`

Hypothesis:
- Windows pairing/consumption behavior may improve if metadata becomes more conservative or more obviously HID-compatible.

Only test H3 after H1 and H2 because it is lower signal and easier to overfit.

---

## Validation Rules

For every round:
1. Change exactly one identity-related aspect.
2. Run local tests.
3. Build both compile targets.
4. Have Windows run one capture.
5. Compare behavior against the previous capture.
6. If behavior worsens, revert that round before trying the next hypothesis.

Success evidence can be any of:
- Windows Settings no longer loops on reconnect/failure.
- BLE connection reaches `connected_idle` more reliably / disconnect storm reduces.
- Windows visibly consumes rotate/press.
- Analysis report and capture log show stable `hid=sent ready=yes` during the same window as successful Windows-side behavior.

---

## Task 1: Freeze a descriptor/identity baseline note

**Objective:** Record the exact current BLE identity settings so each validation round is attributable.

**Files:**
- Modify: `/home/zza/projects/esp32s3_touch_dial/docs/plans/2026-07-04-ble-minimal-descriptor-appearance-tuning-plan.md`
- Read: `/home/zza/projects/esp32s3_touch_dial/esp32s3_touch_dial.ino`

**Implementation details:**
Record these baseline values before any changes:
- advertising appearance = `GENERIC_HID`
- top-level usage = `System Multi-Axis Controller`
- child relative input usage = `Dial`
- report ID = `10`
- BLE name = `ESP32-S3 Touch Dial`
- PnP = `(0x02, 0x303A, 0x1001, USB_FW_VERSION_BCD)`
- HID info = `(0x00, 0x01)`

**Verification:**
- No code changes.
- Baseline note must be present in the plan or commit message before round 1.

---

## Task 2: Add explicit descriptor-profile constants before behavior changes

**Objective:** Make minimal tuning rounds easier to apply and revert without rewriting logic.

**Files:**
- Modify: `/home/zza/projects/esp32s3_touch_dial/esp32s3_touch_dial.ino`
- Test: existing compile matrix only

**Step 1: Introduce identity constants**
Add compact constants near the descriptor/USB identity section for:
- advertised BLE appearance
- optional descriptor profile selector
- optional product name override if later needed

Prefer a shape like:
- `constexpr uint16_t BLE_DIAL_APPEARANCE = GENERIC_HID;`
- `enum class BleDialDescriptorProfile : uint8_t { Baseline, VariantA, VariantB };`
- `constexpr BleDialDescriptorProfile BLE_DIAL_DESCRIPTOR_PROFILE = BleDialDescriptorProfile::Baseline;`

Do not change behavior yet.

**Step 2: Route existing calls through constants**
Replace direct literals only where identity is declared, for example:
- `setAppearance(BLE_DIAL_APPEARANCE)`
- choose descriptor bytes from a helper or selected static array

**Verification:**
Run:
- `rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q`
- `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial`
- `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial`

Expected:
- All tests pass.
- Both builds pass.
- No behavior change intended yet.

---

## Task 3: Round 1 — appearance-only tuning

**Objective:** Test whether Windows behavior improves from a pure advertisement identity change with zero report semantic change.

**Files:**
- Modify: `/home/zza/projects/esp32s3_touch_dial/esp32s3_touch_dial.ino`

**Change scope:**
Only adjust advertisement appearance. Do not touch the report descriptor in this round.

**Recommended approach:**
- Keep the descriptor unchanged.
- Replace `GENERIC_HID` with one conservative alternative chosen from the Arduino/ESP BLE appearance constants available in the environment.
- If no appropriate dial-specific constant exists, first test a more neutral but still HID-adjacent appearance only if it can be justified and kept isolated.

**Important:**
Do not invent a magic number unless it is backed by an imported SDK constant or clearly documented in code comments.

**Local verification:**
Run the same 3 commands from Task 2.

**Windows validation script for this round:**
- Flash / deploy the build.
- Start one Windows run:
  - `tools\run_ble_validation_and_analyze.bat COM15 60`
- In the 60-second window:
  - Open Windows Settings Bluetooth page.
  - Attempt device connection once.
  - After any successful connected window, rotate left/right and press a few times.

**Round-1 acceptance questions:**
- Does Settings still loop on `请尝试重新连接设备`?
- Does first connection stay up longer?
- Is there less disconnect churn?
- Any visible system/app reaction to rotate/press?

**Decision:**
- If improved, keep this appearance change and move to a fresh validation round.
- If unchanged or worse, revert and proceed to descriptor-only tuning.

---

## Task 4: Round 2 — descriptor top-level usage tuning only

**Objective:** Test whether Windows better accepts/consumes the device when the top-level HID identity is made more conservative or more directly aligned with dial semantics.

**Files:**
- Modify: `/home/zza/projects/esp32s3_touch_dial/esp32s3_touch_dial.ino`

**Change scope:**
Change only the report descriptor profile. Keep advertisement appearance fixed at the best known value from Task 3 or baseline if Task 3 failed.

**Constraints:**
- Preserve report size and event semantics if possible:
  - 1 button bit + padding + 1 signed relative dial delta
- Do not simultaneously alter throttling, send timing, or backend state logic.
- Prefer the smallest descriptor delta that changes only the identity/usage interpretation.

**Suggested profile strategy:**
Implement two static descriptors and choose one via a profile constant.

Baseline profile:
- current `System Multi-Axis Controller` + `Dial`

Variant profile:
- a more conservative HID shape intended to test Windows acceptance while preserving relative rotation + press semantics
- document exactly what changed and why in comments

**What to avoid in this round:**
- No new reports.
- No multiple report IDs.
- No touch/menu/extra buttons.
- No consumer-control hybrid descriptor yet.

**Local verification:**
Run the same 3 commands from Task 2.

**Windows validation:**
Repeat one 60-second capture with real rotate/press activity.

**Decision:**
- If Windows consumption appears, keep the variant.
- If connection stability improves but consumption still fails, note it and continue.
- If regression occurs, revert before next round.

---

## Task 5: Round 3 — metadata-only tuning (PnP / HID info / name), only if needed

**Objective:** Test whether conservative metadata changes affect pairing acceptance without further descriptor churn.

**Files:**
- Modify: `/home/zza/projects/esp32s3_touch_dial/esp32s3_touch_dial.ino`

**Change scope:**
Only adjust one metadata aspect per round:
- PnP tuple
- HID info tuple
- advertised/scanned name formatting

**Rules:**
- Change one field at a time.
- Add a short code comment explaining why the field is being tested.
- Keep descriptor and appearance unchanged from the best current candidate.

**Local verification:**
Run pytest + both compile commands.

**Windows validation:**
One capture per metadata round, not multiple combined changes.

**Decision:**
Stop this phase as soon as one variant produces clearly better pairing/consumption behavior.

---

## Task 6: Tighten analysis output if current reports hide the important failure mode

**Objective:** Ensure future analysis reports surface the difference between `sent`, `skip:not_ready`, and last-state-only fields.

**Files:**
- Modify if needed: `/home/zza/projects/esp32s3_touch_dial/tools/analyze_hid_captures.py`
- Modify if needed: `/home/zza/projects/esp32s3_touch_dial/tests/test_hid_capture_analysis.py`

**Problem statement:**
Current JSON fields like `last_backend_error` and `last_send_type` only reflect the last observed state, but the log may contain earlier skipped sends and later successful sends in the same capture.

**Possible minimal enhancements:**
- count `>BLE report skip reason=not_ready`
- count successful `hid=sent`
- include booleans like:
  - `observed_ble_send_success`
  - `observed_ble_send_not_ready_skip`
  - `observed_ble_press_sent`
  - `observed_ble_rotate_sent`

**Verification:**
- Add failing pytest first.
- Re-run full tests.
- Keep this separate from descriptor tuning unless analysis blindness blocks decision-making.

---

## Automated Test Strategy

### Python regression commands
Run after every meaningful increment:
- `rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q`

### Build matrix
Run after every meaningful increment:
- `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial`
- `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial`

### Coverage matrix
- `esp32s3_touch_dial.ino`
  - compile verification via both targets
- `tools/analyze_hid_captures.py`
  - `tests/test_hid_capture_analysis.py`
- BLE init / ordering regression
  - `tests/test_ble_backend_init_order.py`

### TDD order for any tool changes
1. Write failing pytest fixture for desired report behavior.
2. Run targeted pytest to confirm failure.
3. Implement minimal parser/report change.
4. Run targeted pytest.
5. Run full pytest.

---

## Manual Device Validation Matrix

For every Windows round, record all four dimensions:

### A. Pairing / Settings behavior
- Device discoverable: yes/no
- First connect attempt succeeds: yes/no
- Settings loops on `请尝试重新连接设备`: yes/no
- Reconnect behavior better / same / worse

### B. Firmware BLE state
From `capture.log` / report:
- advertising observed: yes/no
- connected observed: yes/no
- disconnect observed: yes/no
- `backend_status=connected_idle`: yes/no
- `dial_backend_ready=1`: yes/no

### C. Send-path evidence
- `>BLE report rotate ...`: yes/no
- `>BLE report press`: yes/no
- `hid=sent ready=yes`: yes/no
- `skip reason=not_ready`: count / yes-no

### D. Host-visible consumption
- Windows volume OSD reacts: yes/no
- target app reacts: yes/no
- rotate only / press only / both / neither

---

## Optimization Phase (Only After a Better Identity Variant Exists)

Do not begin this until one identity variant is measurably better.

Potential follow-up optimization topics:
- reduce reconnect churn
- improve advertising restart behavior
- de-duplicate repeated `ready_edge` logs
- make descriptor/profile selection clearer in code
- split BLE identity declaration into helper functions for maintainability

These are optimization tasks, not part of the minimal tuning phase.

---

## Rollback Strategy

If a round regresses behavior:
1. Revert only that round’s identity change.
2. Re-run pytest and both compile targets.
3. Confirm firmware returns to known baseline behavior.
4. Try the next hypothesis independently.

Do not stack multiple “maybe fixes” before validation.

---

## Exit Criteria

This plan is complete when one of these becomes true:

1. **Windows accepted + consumed**
- Settings pairing behavior is acceptable
- rotate and press are consumed by Windows or target app
- capture still shows `hid=sent ready=yes`

2. **Descriptor issue proven**
- BLE connection and send path are healthy
- Windows still does not consume inputs
- one or more minimal identity variants clearly change host behavior
- next step can confidently focus on deeper descriptor redesign

3. **Metadata/identity not enough**
- appearance + descriptor + metadata minimal rounds do not materially improve host behavior
- evidence supports moving to a broader compatibility strategy with a new explicit plan

---

## AI Execution Prompt

Use the following prompt verbatim or with only path/date updates:

```text
继续在 /home/zza/projects/esp32s3_touch_dial 内工作，只在这个目录改动。

目标：执行 docs/plans/2026-07-04-ble-minimal-descriptor-appearance-tuning-plan.md，做“最小 descriptor/appearance 调整 + 本地测试/编译验证”。

严格约束：
1. 只做最小、可回退、可归因的 BLE HID identity 调整。
2. 不改编码器扫描逻辑，不改事件模型，不做大重构。
3. 每一轮只改一个维度：appearance、descriptor profile、或 metadata；不要叠加多个猜测改动。
4. 每次有意义改动后都必须实际执行：
   - rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q
   - rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial
   - rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial
5. 如果工具分析输出不足以支撑判断，可以最小增强 tools/analyze_hid_captures.py 和对应 pytest，但必须先写失败测试再实现。
6. 不要伪造 Windows 结果；Linux/本地只能完成代码、pytest、编译、静态检查与日志工具增强。需要 Windows 实机结果时，明确告诉我该跑哪一轮 capture。

执行顺序：
A. 先把当前 BLE identity 提炼成常量/可切换 profile，但不改变行为。
B. 做 Round 1：appearance-only 调整。
C. 跑 pytest + 双 compile，汇报改动点、命令结果、需要我在 Windows 上执行的 capture 指令。
D. 如果我给回 Windows capture，再基于证据决定是否进入 Round 2 descriptor-only 调整。
E. 如果 analysis report 仍掩盖 sent/skip 历史，先补工具测试和最小分析增强。

输出要求：
- 先给出本轮你理解的目标和执行计划。
- 真正改文件并运行命令，不要只写建议。
- 汇报时必须包含：改了哪些文件、每个命令真实输出摘要、当前推荐的 Windows 验证动作。
- 始终保持变更最小且可回滚。
```

---

## Suggested Commit Message Templates

- `docs: add BLE minimal descriptor tuning plan`
- `refactor: extract BLE HID identity constants`
- `feat: add BLE appearance-only tuning variant`
- `feat: add BLE descriptor profile switch for Windows validation`
- `test: extend HID capture analysis for BLE send outcome visibility`

---

## Operator Notes

When asking the Windows side to validate, keep instructions minimal:
- run exactly one capture
- use one known COM port
- perform rotate + press during the connected window
- return `analysis_report.json` and `capture.log`

This keeps each round attributable and prevents evidence from being blurred by repeated manual retries.
