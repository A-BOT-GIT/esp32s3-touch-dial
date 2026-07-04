# ESP32-S3 Surface Dial / Windows Radial Controller 模拟项目计划文档集

版本：v1.2  
更新日期：2026-07-04  
目标设备：ESP32-S3 + 旋钮编码器 + 按键  
主目标：让 Windows 把 ESP32 识别并消费为 Surface Dial / Radial Controller 类设备，而不是普通媒体键旋钮。

---

## v1.1 核心更新

根据最新实机日志，计划已更新：

```text
SC_BOND + IO_NONE 保留
BLEDevice::setEncryptionLevel(ESP_BLE_SEC_ENCRYPT) 默认禁用
CCCD 0x2902 / Report Reference 0x2908 权限补丁保留
Consumer Control / Media Dial 作为稳定 BLE HID 诊断基线
正式 Surface Dial 主线从 no-force-encryption 稳定 BLE 初始化策略开始
```

最新稳定基线特征：

```text
[BLE-HID] security: SC_BOND + IO_NONE
[BLE-HID] force encryption level: disabled
connected=2
disconnected=0
hid_sent=86
hid_skip=0
```

这说明前一轮连接抖动的主要原因不是 B+C 映射本身，而是强制 `setEncryptionLevel()` 导致 Windows / ESP32 bonding 或 encryption 状态不一致。

---

## v1.2 核心更新

本版在 v1.1 的路线和决策基础上，增加了更具体的技术实现细节：

```text
1. ESP32 固件模块拆分建议
2. BLE 初始化伪代码和调用顺序
3. Radial Controller HID descriptor 字节级说明
4. BLE HOGP characteristic / ReportRef / CCCD 结构
5. 2-byte radial payload 的编码、边界、测试用例
6. 编码器按键状态机：press / release / hold / rotate while pressed
7. Windows Radial Probe 的 C# / UWP 实现骨架
8. 串口日志与事件对照格式
9. Agent 可执行的代码改造任务清单
```

新增重点文件：

| 文件 | 用途 |
|---|---|
| `10_TECHNICAL_IMPLEMENTATION_DETAILS.md` | 固件实现细节总说明 |
| `11_HID_DESCRIPTOR_AND_PAYLOAD_DETAILS.md` | HID descriptor 与 payload 字节级细节 |
| `12_ENCODER_BUTTON_STATE_MACHINE.md` | 旋钮编码器和按钮状态机设计 |
| `13_WINDOWS_RADIAL_PROBE_IMPLEMENTATION.md` | Windows Radial Probe 实现方案 |
| `14_AGENT_IMPLEMENTATION_TASKS_DETAILED.md` | 更细的 agent 代码改造任务书 |

---

## 文档结构

| 文件 | 用途 |
|---|---|
| `00_PROJECT_DECISION_RECORD.md` | 项目阶段结论、最新 no-force-encryption 决策、失败分支修正 |
| `01_ROADMAP.md` | 后续总体路线图，从 no-force-encryption 基线到完整 Surface Dial |
| `02_FIRMWARE_RADIAL_MVP_SPEC.md` | ESP32 固件侧 Radial Controller MVP 详细实现规范 |
| `03_BLE_HOGP_REPORT_RULES.md` | BLE HID over GATT 报告、Report ID、Report Reference、缓存和加密策略 |
| `04_WINDOWS_RADIAL_PROBE_SPEC.md` | Windows 端 RadialController 验证程序设计 |
| `05_VALIDATION_AND_DEBUG_PLAYBOOK.md` | 实测、日志、断连、Windows 缓存、串口抓取排障手册 |
| `06_AGENT_TASKS.md` | 可以直接交给本地 Agent 执行的分阶段任务书 |
| `07_ACCEPTANCE_CRITERIA.md` | 每个阶段的验收标准和不通过时的处理方式 |
| `08_BRANCHING_AND_RELEASE_PLAN.md` | Git 分支、tag、提交、回退、发布策略 |
| `09_CHANGELOG_V1_1.md` | v1.1 修改摘要 |
| `10_TECHNICAL_IMPLEMENTATION_DETAILS.md` | 固件技术实现细节 |
| `11_HID_DESCRIPTOR_AND_PAYLOAD_DETAILS.md` | HID descriptor 与 payload 字节细节 |
| `12_ENCODER_BUTTON_STATE_MACHINE.md` | 编码器 / 按钮状态机 |
| `13_WINDOWS_RADIAL_PROBE_IMPLEMENTATION.md` | Windows Radial Probe 实现方案 |
| `14_AGENT_IMPLEMENTATION_TASKS_DETAILED.md` | 详细 agent 实施任务 |

---

## 一句话原则

Consumer Control 音量分支只作为 BLE HID 传输诊断基线；正式目标应回到 Microsoft Radial Controller HID 协议：Button 控制菜单，Dial 控制动作。

---

## 当前推荐下一步

1. 将 no-force-encryption 状态冻结为稳定 BLE HID 诊断基线。
2. 建议分支 / tag：
   ```bash
   git branch test/ble-consumer-volume-no-force-encrypt-working
   git tag ble-hid-no-force-encrypt-working
   ```
3. 从该稳定 BLE 初始化策略创建：
   ```bash
   feature/ble-radial-controller-mvp
   ```
4. 在 Radial MVP 分支中替换：
   ```text
   Media Report ID 2              -> RADIAL_REPORT_ID 1
   ReportRef 02 01                -> ReportRef 01 01
   Consumer Control 1-byte report -> Radial Controller 2-byte report
   Consumer Control usages        -> System Multi-Axis Controller + Button + Dial
   ```
5. 用 Windows Radial Probe 验证 `RotationChanged` / `ButtonClicked`，不要用系统音量变化作为 Surface Dial 成功标准。
