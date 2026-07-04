# 04 Windows Radial Probe 验证程序设计

## 1. 为什么需要 Windows Probe

Surface Dial / Radial Controller 的成功标准不是系统音量变化。Consumer Control 音量键验证的是普通媒体键。Surface Dial 验证的是 Windows RadialController 输入系统。

因此需要一个最小 Windows 测试程序：

```text
tools/win_radial_probe/
```

用于确认：Windows 是否把 ESP32 当作 radial controller；是否能收到 ButtonClicked；是否能收到 RotationChanged；菜单是否能出现。

## 2. 推荐技术路线

优先路线：

```text
UWP / WinUI / C# RadialController API
```

原因：RadialController API 是 Windows 官方 wheel 交互入口；比直接读 HID 更接近真实应用行为。

## 3. Probe 功能需求

### 3.1 UI

窗口包含：当前连接状态文本；最近事件列表；Rotation delta 累计值；Button click 计数；清空日志按钮；导出日志按钮。

### 3.2 RadialController 功能

程序启动时：

1. 创建 RadialController；
2. 配置菜单；
3. 添加自定义 tool：`ESP32 Probe`；
4. 注册事件。

建议事件：

```text
RotationChanged
ButtonClicked
ControlAcquired
ControlLost
ScreenContactStarted
ScreenContactContinued
ScreenContactEnded
ButtonHolding / ButtonPressed / ButtonReleased
```

具体 API 可用性按 Windows SDK 实际情况调整。

## 4. Probe 日志格式

```text
[16:55:01.123] RotationChanged delta=1 cumulative=12
[16:55:02.456] ButtonClicked count=3
[16:55:03.789] ControlAcquired
[16:55:04.111] ControlLost
```

保存为：

```text
tools/win_radial_probe/logs/radial_probe_YYYYMMDD_HHMMSS.txt
```

## 5. 验证流程

### 5.1 启动前

1. 烧录 `feature/ble-radial-controller-mvp`；
2. Windows 蓝牙连接 `ESP32-S3 Radial MVP`；
3. 打开串口抓取；
4. 启动 Radial Probe。

### 5.2 操作

| 操作 | 预期 |
|---|---|
| 旋转右 | Probe 出现 `RotationChanged delta > 0` |
| 旋转左 | Probe 出现 `RotationChanged delta < 0` |
| 短按 | Probe 出现 Button 事件 |
| 长按 | Windows radial menu 或相关 holding 行为 |
| 菜单打开后旋转 | 菜单项变化或 probe 事件变化 |

## 6. Probe 与串口日志对照

旋转右：

```text
>BLE radial report len=2 data=02 00 button=0 delta=1 hid=sent
RotationChanged delta=...
```

旋转左：

```text
>BLE radial report len=2 data=FE FF button=0 delta=-1 hid=sent
RotationChanged delta=...
```

按下/释放：

```text
>BLE radial report len=2 data=01 00 button=1 delta=0 hid=sent
>BLE radial report len=2 data=00 00 button=0 delta=0 hid=sent
ButtonClicked 或 ButtonPressed/ButtonReleased
```

## 7. 如果 Probe 收不到事件

按顺序排查：Windows 设备管理器是否出现 HID-compliant device；是否仍是旧设备名；是否连接稳定；串口是否 `hid=sent`；Report Reference 是否 `01 01`；BLE notify value 是否 2 字节；Report Map 是否使用 `System Multi-Axis Controller 0x0E`；Dial 是否 Relative；Button 是否按下后释放；Probe 是否前台获得焦点。

## 8. 可选：Raw HID Probe

如果 RadialController API 不收事件，但设备被 HID 枚举，可以后续做 Raw HID probe：枚举 HID devices、读取 HID report descriptor、打印 input report、确认 Windows HID 层是否收到 `02 00` / `FE FF`。
