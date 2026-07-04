# ESP32-S3 Radial MVP Stable Baseline — delta60

> 验证日期：2026-07-05
> 分支：`feature/ble-radial-controller-mvp`
> 标签：`radial-mvp-native-menu-volume-working-delta60`

## 设备枚举

| 字段 | 值 |
|------|-----|
| Product | ESP32-S3 Radial MVP |
| Usage | 0x0001:0x000E (Generic Desktop / System Multi-Axis Controller) |
| VID | 0x303A (Espressif) |
| PID | 0x0110 |

## 固件关键参数

| 参数 | 值 |
|------|-----|
| Report ID | 1 |
| Report Reference | 01 01 |
| Report Map 大小 | 56 bytes |
| 描述符 | System Multi-Axis Controller + Digitizers/Puck + Button + Dial 15-bit |
| BLE payload | 2 bytes，不含 Report ID |
| 旋转灵敏度 | `RADIAL_DETENT_TENTHS_DEG = 60`（每格 6.0°） |
| 强制加密 | disabled |
| Security | SC_BOND + IO_NONE |
| CCCD/2902 | READ\|WRITE |
| ReportRef/2908 | READ only |
| Consumer Control | 已移除 |

## Raw HID 验证

```
操作          | bytes       | 含义
-------------|-------------|------------------
释放         | 01 00 00    | button=0 delta=0
按下         | 01 01 00    | button=1 delta=0
右转         | 01 78 00    | button=0 delta=+60
左转         | 01 88 FF    | button=0 delta=-60
按下右转     | 01 79 00    | button=1 delta=+60
按下左转     | 01 89 FF    | button=1 delta=-60
```

## Windows Radial Probe 验证

| 事件 | 状态 |
|------|------|
| MenuItem Invoked (ESP32 Probe) | ✅ |
| ControlAcquired | ✅ |
| RotationChanged | ✅ |
| ButtonPressed | ✅ |
| ButtonReleased | ✅ |
| ButtonClicked | ✅ |

## Windows 原生 Radial 菜单验证

| 操作 | 结果 |
|------|------|
| 长按弹出菜单 | ✅ |
| 旋转切换菜单项 | ✅ |
| 选择"音量"后旋转调音量 | ✅ |

## 已知限制

1. Windows 原生"滚动"和"缩放"在普通网页/文档中可能无效
2. 这是 Windows RadialController 对前台应用支持有限，不是 ESP32 BLE HID 链路问题
3. 如需全局滚动/缩放，应另开 Windows Companion 增强程序分支

## 诊断工具

| 工具 | 路径 |
|------|------|
| Raw HID Probe | `tools/win_raw_hid_probe/hid_probe.py` |
| Windows Radial Probe | `tools/win_radial_probe/` |
| Serial Capture | `tools/capture_esp32_ble_hid_serial_v4.ps1` |
| 计划文档 | `docs/esp32_surface_dial_plan_docs_v1_2/` |

## 编译验证

| 目标 | 结果 |
|------|------|
| BLE (`esp32:esp32:esp32s3`) | ✅ 945793 bytes |
| USB+CDC | ✅ 339281 bytes |
| pytest | ✅ 44 passed |
