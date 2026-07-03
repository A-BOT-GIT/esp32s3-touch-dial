# BLE Dial Backend Handoff

项目路径：`/home/zza/projects/esp32s3_touch_dial`

## 当前状态

已完成：
- git / GitHub 已就绪
- GitHub Actions 已加
- `pytest` 已通过
- `arduino-cli compile` 双目标已通过
- USB PoC 的 Dial backend 抽象已完成
- BLE Dial backend 已从占位骨架推进到“真实 init / advertising / connect-disconnect 状态机骨架”
- Phase A 第一批（可观测性增强）已完成
- BLE HID init 启动崩溃已修复（`manufacturer()` characteristic 先创建再 setValue）
- Linux 侧已完成真实烧录与串口实测，确认可进入 BLE advertising，不再在 `>BLE init` 后 panic 重启

当前 BLE backend 已具备：
- `beginDialBackend()` 内真实执行 BLE init
- BLE HID service 创建
- advertising 启动
- connect / disconnect 回调
- `dial_backend_ready` 随连接状态切换
- 最小 rotate / press notify 发送骨架
- 串口日志可见 BLE 关键事件
- `HID_STATUS` / `ENC_STATUS` 已包含 BLE 关键状态字段

## 本轮新增能力

### 固件侧
文件：`esp32s3_touch_dial.ino`

新增/完善：
- 显式 BLE 状态枚举：
  - `Uninitialized`
  - `Initializing`
  - `Advertising`
  - `ConnectedIdle`
  - `SendingRotate`
  - `SendingPress`
  - `RestartingAdvertising`
  - `Error`
- BLE 状态字段：
  - `ble_connected`
  - `ble_advertising`
  - `last_backend_error`
  - `last_send_type`
- BLE 事件日志：
  - `>BLE init`
  - `>BLE advertising start`
  - `>BLE advertising restart`
  - `>BLE connected`
  - `>BLE disconnected`
  - `>BLE report rotate delta=...`
  - `>BLE report press`
  - `>BLE report skip reason=...`
- `HID_STATUS` 新增字段：
  - `ble_connected`
  - `ble_advertising`
  - `last_backend_error`
  - `last_send_type`
- `ENC_STATUS` 新增字段：
  - `ble_connected`
  - `ble_advertising`
  - `last_send_type`

### Python 分析工具侧
文件：`tools/analyze_hid_captures.py`

已支持解析并展示：
- `dial_backend`
- `dial_backend_ready`
- `backend_status`
- `ble_connected`
- `ble_advertising`
- `last_backend_error`
- `last_send_type`

### 测试侧
文件：`tests/test_hid_capture_analysis.py`、`tests/test_ble_backend_init_order.py`

现有 BLE 相关测试包括：
- BLE backend not-ready 样例
- BLE backend ready 样例
- BLE advertising 状态字段样例
- BLE HID manufacturer characteristic 初始化顺序回归测试

## 最近验证结果

### pytest
命令：
`rtk proxy python3 -m pytest /home/zza/projects/esp32s3_touch_dial/tests -q`

结果：
- `26 passed in 0.11s`

### BLE / hwcdc 编译
命令：
`rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' /home/zza/projects/esp32s3_touch_dial`

结果：
- 通过
- `Sketch uses 942385 bytes (71%)`

### USB TinyUSB 编译
命令：
`rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3:USBMode=default,CDCOnBoot=cdc' /home/zza/projects/esp32s3_touch_dial`

结果：
- 通过
- `Sketch uses 338997 bytes (25%)`

### Linux 实机烧录 / 启动验证
实测结论：
- `arduino-cli upload` 在当前原生 USB 路径上收尾阶段仍可能报：
  - `A fatal error occurred: Packet content transfer stopped (received 25 bytes)`
- 该错误不应直接当作“应用未写入”的充分证据；本轮已改用保守 `esptool.py --no-stub write_flash` 流程完成稳定刷写
- 保守刷写后已抓到真实启动串口，关键日志为：
  - `>PROBE setup.begin`
  - `>BLE init`
  - `>BLE advertising start`
  - `>HID_STATUS reason=ble_advertising_start ... backend_status=advertising ... ble_advertising=1 ... last_backend_error=none`
  - `>PROBE setup.done`
  - `>HELLO`

结论：
- 当前 BLE backend 不再在 init 阶段崩溃
- Linux 侧已实证进入 `advertising`
- 下一步可以进入 Windows BLE discovery / pairing / rotate / press / reconnect 实机验证

## 必须遵守的约束

- 只在 `/home/zza/projects/esp32s3_touch_dial` 工作
- 每步都验证：
  - `pytest`
  - BLE/hwcdc compile
  - USB TinyUSB compile
- 不能让 USB 路径回归
- 优先做增量修改，不要一次性大重构
- 若新增行为，先补测试再实现

## 下一步主任务（优先顺序）

### 1. 继续 Phase B：BLE send semantics stabilization
目标：把当前“最小 notify 骨架”推进到更稳定、可调试的发送层

建议先做：
- 抽 helper：
  - `bleDialSendReport(uint8_t buttons, int8_t delta, const char* send_type)`
  - `bleDialSendReleaseReport()`
- 去掉 rotate / press 发送逻辑重复代码
- 统一 skip/error 原因记录
- 明确 send 后状态回切到 `ConnectedIdle`

### 2. 加发送节流
已完成：
- BLE rotate 最小发送间隔
- BLE press 最小发送间隔
- skip reason 已扩展到：
  - `rate_limited_rotate`
  - `rate_limited_press`

结果：
- 避免高频 notify 导致拥塞
- 为 Windows 实机验证提供更稳定、可解释的行为

### 3. 补更多测试/样例
已完成/已覆盖：
- `last_send_type=rotate_right`
- `last_send_type=press`
- `last_backend_error=not_ready`
- `last_backend_error=report_missing`
- `last_backend_error=rate_limited_rotate`
- `last_backend_error=rate_limited_press`

### 4. 然后进入 Windows 实机验证准备
已完成：
- BLE validation matrix 文档
- 配对 / 重连 / ready / rotate / press 验证步骤

当前下一步：
- 在 Windows 上按验证矩阵执行首轮 BLE discovery / pairing / rotate / press / reconnect 实机验证
- 将结果回填到 `docs/plans/2026-07-03-ble-dial-validation-matrix.md`

## Linux 保守刷写路径（当前已验证可用）

当 `arduino-cli upload` 收尾不稳定时，使用以下流程：

1. 固定 BLE build 目录编译：
   - `rtk proxy arduino-cli compile --fqbn 'esp32:esp32:esp32s3' --build-path /tmp/esp32s3_touch_dial_ble_runfix /home/zza/projects/esp32s3_touch_dial`
2. 使用核心自带 `esptool.py` 手工刷写：
   - `python3 /home/zza/.arduino15/packages/esp32/tools/esptool_py/4.5.1/esptool.py --chip esp32s3 --port /dev/ttyACM0 --baud 115200 --before default_reset --after hard_reset --no-stub write_flash --flash_mode dio --flash_freq 80m --flash_size 4MB 0x0 /tmp/esp32s3_touch_dial_ble_runfix/esp32s3_touch_dial.ino.bootloader.bin 0x8000 /tmp/esp32s3_touch_dial_ble_runfix/esp32s3_touch_dial.ino.partitions.bin 0xe000 /home/zza/.arduino15/packages/esp32/hardware/esp32/2.0.17/tools/partitions/boot_app0.bin 0x10000 /tmp/esp32s3_touch_dial_ble_runfix/esp32s3_touch_dial.ino.bin`
3. 刷写后立即抓串口确认：
   - `>BLE advertising start`
   - `backend_status=advertising`
   - `ble_advertising=1`

## 推荐执行顺序

1. 先补一个失败测试：分析工具识别 `last_send_type` / `last_backend_error` 的更具体语义
2. 实现 BLE send helper
3. 跑 `pytest`
4. 跑 BLE/hwcdc compile
5. 跑 USB TinyUSB compile
6. 再继续下一小步

## 相关文档

- 后续总计划：
  - `docs/plans/2026-07-03-ble-dial-backend-followup-plan.md`
- 本交接文档：
  - `docs/plans/2026-07-03-ble-dial-backend-handoff.md`
- 旧计划/上下文：
  - `docs/plans/2026-07-03-surface-dial-github-route-decision.md`
  - `docs/plans/2026-07-03-encoder-screen-surface-dial-execution-plan.md`
  - `docs/plans/2026-07-03-task1-event-model-freeze.md`

## 新会话接手时建议先读

1. `docs/plans/2026-07-03-ble-dial-backend-handoff.md`
2. `docs/plans/2026-07-03-ble-dial-backend-followup-plan.md`
3. `esp32s3_touch_dial.ino`
4. `tools/analyze_hid_captures.py`
5. `tests/test_hid_capture_analysis.py`
