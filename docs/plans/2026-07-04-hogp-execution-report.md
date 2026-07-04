# HOGP Radial Controller 任务执行汇报

> 日期: 2026-07-04 | 项目: esp32s3_touch_dial | 分支: main

---

## 1. 执行的计划文件

- 第一轮: `docs/plans/2026-07-04-ble-minimal-descriptor-appearance-tuning-plan.md`
- 第二轮: `docs/plans/esp32_ble_hogp_radial_controller_agent_task.md`

---

## 2. 执行结果总览

| 指标 | 状态 | 说明 |
|------|------|------|
| 编译 BLE (esp32:esp32:esp32s3) | ✅ PASS | 944857 bytes (72%) |
| 编译 USB+CDC | ✅ PASS | 338997 bytes (25%) |
| pytest | ✅ 41 passed | 32 原有 + 9 新增 |
| BLE 配对 | ✅ 成功 | Just Works bonding |
| BthLEEnum 驱动错误 | ✅ 已消除 | 不再显示驱动程序错误 |
| Windows HID 驱动加载 | ✅ 已加载 | 设备管理器显示 HID 设备 |
| Radial Controller 完整识别 | ❌ 未达成 | 显示为通用 HID (键鼠图标) |
| HID 报告被 Windows 消费 | ❌ 未验证 | 需要在连接窗口内操作编码器 |

---

## 3. 已完成的修改任务

### Task A: BLE Security → Bonded Just Works ✅

- `ESP_LE_AUTH_NO_BOND` → `ESP_LE_AUTH_REQ_SC_BOND` (fallback `ESP_LE_AUTH_BOND`)
- 配置 `ESP_IO_CAP_NONE` + `setEncryptionLevel(ESP_BLE_SEC_ENCRYPT)`
- 代码中不再出现 `ESP_LE_AUTH_NO_BOND` 作为主路径

### Task B: 稳定 BLE 地址 ✅

- `fillBleDialRandomAddress()` 从 `esp_random()` 改为 `esp_read_mac(ESP_MAC_BT)` 派生
- 加入 `ESP_MAC_WIFI_STA` fallback
- `addr[0] | 0xC0` 满足 BLE random static address 格式

### Task C: 3 服务 16-bit 广告 ✅

- 自定义 AD 元素 `{0x07, 0x03, 0x12, 0x18, 0x0F, 0x18, 0x0A, 0x18}`
- 包含 HID (0x1812) + Battery (0x180F) + Device Information (0x180A)
- Appearance 在 primary AD，Name 在 scan response
- Primary AD 总计约 19 字节，未超 31 字节限制
- 未使用 `addServiceUUID()` (会转 128-bit 导致溢出)

### Task D: Radial Controller 最小描述符 ✅

- Report ID = 1
- Usage Page: Generic Desktop, Usage: System Multi-Axis Controller (0x0E)
- Button 1 (1 bit, Button Page) + Dial (15 bit signed, ±3600, 0.1 degree units)
- 描述符数组: `radialControllerReportMap`

### Task E: CCCD / Report Reference 权限补丁 ✅

- Input Report characteristic: 保持加密权限 (库默认)
- CCCD (0x2902): `ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE` (开放)
- Report Reference (0x2908): `ESP_GATT_PERM_READ | ESP_GATT_PERM_WRITE` (开放)
- 补丁在 `startServices()` 前执行

### Task F: Device Information Service ✅

- PnP ID: `(0x02, 0x303A, 0x1001, 0x0100)`
- HID Info: `(0x00, 0x01)`
- Manufacturer: `"zza"`

### Task G: 3 字节 Radial Controller 报告格式 ✅

- `report[0]` = Report ID (1)
- `report[1..2]` = 16-bit payload (bit0=button, bit1-15=signed 15-bit dial)
- `buildDialReport()` 辅助函数
- USB HID 路径同步更新

### Task H: 调试日志 ✅

- `[BLE-HID]` 前缀的结构化日志
- 覆盖: init, security, address, report id, report map size, input report created, descriptor permissions, services started, advertising started, connected, disconnected, notify report

### Task I: 测试更新 ✅

新增 9 个测试:
- `test_ble_security_uses_bonded_just_works_not_no_bond`
- `test_ble_security_uses_sc_bond_or_bond`
- `test_dial_report_id_is_one`
- `test_radial_controller_descriptor_structure`
- `test_cccd_and_report_reference_permissions_patched`
- `test_report_send_uses_3_byte_format`
- `test_advertising_has_three_16bit_services`
- `test_no_add_service_uuid_for_multi_service`
- `test_no_esp_random_for_address`

---

## 4. 调试过程中发现并修复的问题

| # | 问题 | 根因 | 状态 |
|---|------|------|------|
| 1 | 每次重启 Windows 配对失效 | `esp_random()` 生成真随机地址 | ✅ 已修复 |
| 2 | "请尝试重新连接设备" 循环 | Input Report 加密权限 + 无 IO 能力 | ✅ 已修复 |
| 3 | 配对永远失败 | 默认 MITM 要求与 IO_CAP_NONE 冲突 | ✅ 已修复 |
| 4 | 广告 UUID 被截断 | `addServiceUUID` 转 128-bit 溢出 31 字节 | ✅ 已修复 |
| 5 | BthLEEnum 驱动错误 | 广告只有 HID 服务，缺少 Battery + DIS | ✅ 已修复 |
| 6 | 通用 HID 而非 Radial Controller | Windows 无专用 Radial Controller 类驱动 | ⚠️ 待定 |

---

## 5. 尝试过但无效的变体

| 变体 | 结果 |
|------|------|
| HID_JOYSTICK 外观 | 连接抖动未改善 |
| Multi-axis Controller (0x08) 描述符 | 连接抖动略差 |
| Mouse + Wheel 描述符 | 驱动错误 |
| 1 字节 X 轴最简描述符 | 驱动错误 |
| 公共地址 (不设 random) | 驱动错误 |
| Name 在 primary AD | 驱动错误 |
| 仅 HID+Battery 双服务 | 驱动错误 |
| NO_BOND 配对 | 驱动错误 (HID 需要 bonding) |

---

## 6. 当前代码快照

```
DIAL_REPORT_ID              = 1
BLE_DIAL_APPEARANCE         = 0x03C0 (GENERIC_HID)
描述符                      = radialControllerReportMap (System Multi-Axis Controller + Dial)
BLE 安全模式                = SC_BOND + IO_CAP_NONE + ENCRYPT
BLE 地址                    = BT MAC 派生 random static
广告服务                     = 0x1812, 0x180F, 0x180A (16-bit)
Input Report 特征权限        = 加密 (库默认)
CCCD (0x2902) 权限           = READ | WRITE (开放)
Report Reference (0x2908) 权限 = READ | WRITE (开放)
报告格式                     = 3 bytes [ReportID][payload_lo][payload_hi]
```

---

## 7. 已知剩余问题

1. **Windows 加载通用 HID 驱动而非 Radial Controller 驱动**: System Multi-Axis Controller usage 在 Windows 上没有专用类驱动，显示键鼠图标是预期行为
2. **HID 报告消费未验证**: 需要在 BLE 连接窗口内操作编码器并运行 capture 确认 `hid=sent` 是否出现
3. **报告发送格式可能需要微调**: 15-bit dial 的 scale factor 可能需要与物理旋转步进对齐

---

## 8. 文件清单

| 文件 | 改动 |
|------|------|
| `esp32s3_touch_dial.ino` | 全部 Task A-H 改动 |
| `tests/test_ble_backend_init_order.py` | 新增 9 个 HOGP 验证测试 |
| `docs/plans/2026-07-04-ble-hid-debugging-log.md` | 调试日志文档 |
| `docs/plans/esp32_ble_hogp_radial_controller_agent_task.md` | 任务书 |
| `docs/plans/2026-07-04-hogp-execution-report.md` | 本汇报文件 |

---

## 9. Git 状态

- 当前 HEAD: `8620e6b` (refactor: extract BLE HID identity constants...)
- 所有 HOGP 改动保留在工作区，**未提交**
- 提交需要用户明确许可
