# ESP32-S3 Surface Dial / Windows Radial Controller 模拟项目计划文档集

版本：v1.0  
目标设备：ESP32-S3 + 旋钮编码器 + 按键  
主目标：让 Windows 把 ESP32 识别并消费为 Surface Dial / Radial Controller 类设备，而不是普通媒体键旋钮。

## 文档结构

| 文件 | 用途 |
|---|---|
| `00_PROJECT_DECISION_RECORD.md` | 项目阶段结论、已验证成果、失败分支说明 |
| `01_ROADMAP.md` | 后续总体路线图，从稳定 BLE 基线到完整 Surface Dial 模拟 |
| `02_FIRMWARE_RADIAL_MVP_SPEC.md` | ESP32 固件侧 Radial Controller MVP 详细实现规范 |
| `03_BLE_HOGP_REPORT_RULES.md` | BLE HID over GATT 报告、Report ID、Report Reference、Windows 缓存策略 |
| `04_WINDOWS_RADIAL_PROBE_SPEC.md` | Windows 端 RadialController 验证程序设计 |
| `05_VALIDATION_AND_DEBUG_PLAYBOOK.md` | 实测、日志、断连、Windows 缓存、串口抓取排障手册 |
| `06_AGENT_TASKS.md` | 可以直接交给本地 Agent 执行的分阶段任务书 |
| `07_ACCEPTANCE_CRITERIA.md` | 每个阶段的验收标准和不通过时的处理方式 |
| `08_BRANCHING_AND_RELEASE_PLAN.md` | Git 分支、tag、提交、回退、发布策略 |

## 一句话原则

Consumer Control 音量分支只作为 BLE HID 传输基线；正式目标应回到 Microsoft Radial Controller HID 协议：Button 控制菜单，Dial 控制动作。

## 当前推荐下一步

1. 冻结已验证的 Consumer Control 工作状态。
2. 从稳定 BLE HOGP 基线新建 `feature/ble-radial-controller-mvp`。
3. 实现最小 Radial Controller：`System Multi-Axis Controller + Puck + Button + Dial`。
4. BLE notify 只发送 2 字节 Radial payload，不包含 Report ID。
5. 建立 Windows Radial Probe 程序验证 `ButtonClicked` / `RotationChanged`。
6. MVP 成功后再做 haptic / on-screen / 外壳体验。
