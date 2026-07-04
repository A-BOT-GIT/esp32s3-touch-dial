# 07 验收标准

## 1. Phase 0 Consumer Control 诊断基线

| 项目 | 标准 |
|---|---|
| BLE 连接 | 稳定，2 分钟内无大量断开 |
| Windows 响应 | 音量/静音/播放暂停至少一种能响应 |
| 串口 | 有 `hid=sent` |
| 跳过 | `hid_skip = 0` |
| 错误 | 无持续 BT_APPL / BT_BTM 错误刷屏 |

不通过则不作为基线。

## 2. Phase 1 Radial MVP 分支创建

| 项目 | 标准 |
|---|---|
| 分支 | `feature/ble-radial-controller-mvp` |
| 起点 | 稳定 BLE HOGP 基线 |
| Consumer Control | 已移除 |
| Mouse/Joystick | 不存在 |
| BLE security | 未乱改 |

## 3. Phase 2 固件编译和测试

| 项目 | 标准 |
|---|---|
| BLE 编译 | PASS |
| USB+CDC 编译 | PASS |
| pytest | PASS |
| Report Map 测试 | PASS |
| buildRadialPayload 测试 | PASS |
| BLE value 不带 Report ID | PASS |

## 4. Phase 3 BLE 连接实测

| 项目 | 标准 |
|---|---|
| 新设备名 | Windows 显示新 identity |
| 完整地址 | 日志打印 6 字节 |
| 连接 | 2 分钟稳定 |
| 断开 | 不反复刷屏 |
| backend | `dial_backend_ready=1` |
| skip | `hid_skip=0` |

若反复断开：改 identity、确认 report id、确认 report ref、确认只创建一个 input report、回退 Consumer baseline 对照。

## 5. Phase 4 Radial report 实测

| 操作 | 固件日志 |
|---|---|
| 右转 | `data=02 00 button=0 delta=1 hid=sent` |
| 左转 | `data=FE FF button=0 delta=-1 hid=sent` |
| 按下 | `data=01 00 button=1 delta=0 hid=sent` |
| 释放 | `data=00 00 button=0 delta=0 hid=sent` |

## 6. Phase 5 Windows Radial Probe

| 操作 | Probe 结果 |
|---|---|
| 右转 | `RotationChanged` 正向 |
| 左转 | `RotationChanged` 反向 |
| 点击 | Button 事件 |
| 长按 | 菜单或 holding 行为 |
| 菜单打开旋转 | 菜单项或 tool 状态变化 |

## 7. MVP 最终通过标准

全部满足：Windows 连接稳定；串口 radial report 正确；Windows Probe 收到 RotationChanged；Windows Probe 收到 Button event；长按/菜单交互路径可用；没有 Consumer Control 混入；测试全部通过；文档记录清楚。

## 8. 不允许合并的情况

| 情况 | 是否允许合并 |
|---|---|
| 编译失败 | 否 |
| pytest 失败 | 否 |
| 连接反复断开 | 否 |
| hid_skip 大量出现 | 否 |
| 只实现 Consumer Control | 否 |
| Report value 仍带 Report ID | 否 |
| 没有 Windows Probe 验证 | 暂不合并主线 |
| haptic 未完成 | 可合并 MVP，不阻塞 |
