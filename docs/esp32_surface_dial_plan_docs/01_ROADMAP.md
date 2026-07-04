# 01 后续总体路线图

## 总体策略

项目分为 7 个阶段：

1. 冻结稳定 BLE HID 诊断基线；
2. 新建正式 Radial Controller MVP 分支；
3. 实现固件侧最小 Radial HID 描述符和 2 字节报告；
4. 建立 Windows Radial Probe；
5. 做端到端验证；
6. 修复识别、缓存、连接、report 格式问题；
7. 增强 haptic / on-screen / 外观体验。

## Phase 0：冻结已验证 Consumer Control 基线

### 目标

保留一个“Windows 确实能消费 ESP32 BLE HID 报告”的工作状态，后续 Radial 分支调坏时可以回归对照。

### 操作

```bash
git status
git branch --show-current
git branch test/ble-consumer-volume-working
git tag ble-hid-consumer-working
```

如果当前分支已经是 B+C 后的断连版本，不要 tag 当前状态。应从历史中找到：

- 短按能触发静音；
- 旋转能发 `data=01` / `data=02`；
- 连接稳定；
- `hid_sent > 0`；
- `hid_skip = 0`。

## Phase 1：从稳定基线创建 Radial MVP 分支

### 分支命名

```bash
git checkout <stable-hogp-baseline>
git checkout -b feature/ble-radial-controller-mvp
```

### 禁止事项

- 不要从当前 B+C 断连状态继续；
- 不要混入 Consumer Control；
- 不要做 haptic；
- 不要做 on-screen coordinate；
- 不要在第一版里同时支持多种 HID report；
- 不要让 Windows 继续吃旧缓存。

## Phase 2：固件 Radial Controller MVP

### MVP 输入

| 输入 | HID Usage |
|---|---|
| Button | Button Page / Button 1 |
| Dial | Generic Desktop / Dial |

### MVP 报告

BLE notify value：

```text
2 bytes:
bit0      = button
bit1-15   = signed 15-bit dial delta
```

### 示例

| 动作 | BLE notify value |
|---|---|
| 无输入 | `00 00` |
| 按下 | `01 00` |
| 释放 | `00 00` |
| 顺时针 +1 | `02 00` |
| 逆时针 -1 | `FE FF` |

## Phase 3：Windows Radial Probe

Surface Dial 不等于音量键。正式验证必须看 Windows RadialController API 是否收到事件。

### Probe 功能

- 打开一个测试窗口；
- 创建 RadialController；
- 添加 `ESP32 Probe` 菜单项；
- 打印 `ButtonClicked`；
- 打印 `RotationChanged`；
- 打印菜单/控制权事件；
- 输出文本日志。

## Phase 4：端到端验证

验证顺序：

1. Windows 识别新设备名；
2. BLE 连接稳定 2 分钟；
3. 串口看到 radial report；
4. Probe 收到 rotation；
5. Probe 收到 button click；
6. 长按能触发 radial menu；
7. 菜单打开时旋转能切换菜单项；
8. 菜单关闭时旋转能执行当前工具动作。

## Phase 5：故障分流

### A. 设备连接不稳定

优先查：Windows 缓存、BLE 地址和设备名、Report ID / Report Reference、是否有旧 input report characteristic、是否过早调用 encryption。

### B. 连接稳定但 Windows 不识别 Radial

优先查：Report Map、Top-level collection、Mandatory usages、Report Reference、BLE notify 是否多塞 Report ID、Report payload bit packing。

### C. Windows 识别但旋转没事件

优先查：Dial 是否是 Relative、delta 是否非零、delta 符号方向、单位和 logical range、Windows Probe 是否拥有焦点。

## Phase 6：完整 Surface Dial 增强

MVP 成功后再考虑：haptic output、on-screen contact X/Y、模式切换、屏幕 UI、低功耗和自动重连、外壳和手感。

## Phase 7：发布策略

建议最终分为两个可用模式：

```cpp
BLE_MODE_RADIAL_CONTROLLER
BLE_MODE_CONSUMER_VOLUME_DIAGNOSTIC
```

默认启用 Radial Controller。Consumer Volume 只在调试构建中使用。
