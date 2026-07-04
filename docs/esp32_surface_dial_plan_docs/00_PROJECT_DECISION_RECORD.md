# 00 项目阶段结论与决策记录

## 1. 项目目标

最终目标不是普通音量旋钮，而是：

> 使用 ESP32-S3 + 旋钮编码器模拟 Windows Surface Dial / Radial Controller 设备。

目标交互语义：

| 动作 | Surface Dial 语义 |
|---|---|
| 按住 | 打开 Windows RadialController 菜单 |
| 旋转 | 菜单内切换项目，或对当前工具/应用执行动作 |
| 点击 | 选择菜单项或触发应用命令 |
| 菜单关闭时旋转 | 将旋转事件交给当前 app / 当前 radial tool |

因此正式目标不应该长期停留在 Consumer Control 音量键。

## 2. 已验证成果

前期日志已证明：

- BLE 初始化成功；
- Windows 能连接；
- HID over GATT 路径能跑；
- 编码器事件能进入 HID backend；
- 固件能打印 `hid=sent`；
- Windows 能消费 Consumer Control 媒体键。

这些结果说明项目已经越过了最初的“Windows 只加载 BthLEEnum / GenericDevice，不进入 HID 消费链路”的阶段。

## 3. Consumer Control 分支的意义

Consumer Control 分支不是最终产品，但它非常重要。

它证明：

| 能力 | 状态 |
|---|---|
| BLE 配对 / bonding | 已验证 |
| GATT HID service 基础枚举 | 已验证 |
| Input Report characteristic notify | 已验证 |
| Windows 对 BLE HID input report 的消费 | 已验证 |
| ESP32 编码器事件到 HID backend | 已验证 |
| Windows 对短按媒体键响应 | 已验证 |

因此应冻结一个稳定 Consumer Control 状态作为诊断基线。

建议 tag：

```bash
git tag ble-hid-consumer-working
```

或分支：

```bash
git branch test/ble-consumer-volume-working
```

## 4. 当前不应继续基于 B+C 断连状态开发

最近 B+C 分支虽然编译通过，但实机日志显示严重连接抖动：

- `connected` 很多；
- `disconnected` 很多；
- `hid_sent = 0`；
- `hid_skip` 增加；
- 有 `BT_APPL: bta_dm_set_encryption...`；
- 有 `BT_BTM: Device not found`。

这说明该工作区已经不适合作为正式 Radial Controller 起点。

正确做法：

1. 保留它作为失败案例；
2. 不提交；
3. 从稳定 BLE 基线重新切正式 Radial 分支。

## 5. 正式主线决策

正式主线不再继续堆 Consumer Control。

正式主线是：

```text
feature/ble-radial-controller-mvp
```

目标是最小 Windows Radial Controller：

- Top-level collection：Generic Desktop / System Multi-Axis Controller；
- Physical collection：Digitizers / Puck；
- Mandatory inputs：Button + Dial；
- BLE Report ID：1；
- BLE notify value：2 字节 payload，不带 Report ID；
- Windows 端用 RadialController API 验证事件，而不是用系统音量变化作为成功标准。

## 6. 重要决策表

| 议题 | 决策 |
|---|---|
| 继续 Consumer Control？ | 否，只保留为诊断基线 |
| 正式设备类型 | Windows Radial Controller / Surface Dial 类设备 |
| 验证标准 | Windows RadialController API 能收到 Button / Rotation 事件 |
| 是否继续用音量变化验证 | 只用于诊断，不作为最终标准 |
| BLE notify 是否包含 Report ID | 不包含 |
| Radial Controller 初版是否包含 haptic | 不包含，MVP 成功后再做 |
| 是否先做 on-screen puck | 不做，后期增强 |
| 是否提交当前 B+C 断连工作区 | 不提交 |

## 7. 成功定义

MVP 成功不是“音量变化”，而是：

```text
Windows 把 ESP32 识别并消费为 RadialController；
Windows probe app 能收到 RotationChanged；
按钮按下/释放能触发 RadialController 相关事件；
长按能进入 Radial 菜单行为或至少被 Windows/app 识别为 button hold。
```
