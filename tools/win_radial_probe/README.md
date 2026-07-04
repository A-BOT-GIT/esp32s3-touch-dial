# Windows Radial Probe

验证 ESP32-S3 是否被 Windows **RadialController API** 消费为 Surface Dial 类设备。

## 要求

- Windows 10 19041+ 或 Windows 11
- Visual Studio 2022（Community 免费）
- .NET 6.0 SDK + Windows App SDK (WinUI 3)
- 已配对 "ESP32-S3 Radial MVP" BLE 设备

## 打开工程

1. 安装 Visual Studio 2022，勾选 **.NET 桌面开发** 和 **Windows 应用 SDK** 工作负载
2. 双击 `RadialProbe.sln` 在 Visual Studio 中打开
3. 等待 NuGet 包还原完成

## 运行

1. **先确保 ESP32-S3 已连接**：
   - 打开 Windows 蓝牙设置
   - 确认 "ESP32-S3 Radial MVP" 显示为已连接
2. 在 Visual Studio 中按 **F5**（调试运行）或 **Ctrl+F5**（无调试运行）
3. 窗口打开后，顶部状态应显示 **Ready — rotate/press ESP32**
4. 操作 ESP32 编码器：
   - **旋转** → 应出现 `RotationChanged`
   - **短按** → 应出现 `ButtonClicked`（或 `ButtonPressed` / `ButtonReleased`）
   - **长按** → 应出现 `ButtonHolding`，可能触发 Radial 菜单

## 判断 PASS

| 操作 | 预期 Probe 事件 | 对应固件日志 |
|------|----------------|-------------|
| 旋转右 | `RotationChanged delta > 0` | `>BLE radial report ... data=02 00` |
| 旋转左 | `RotationChanged delta < 0` | `>BLE radial report ... data=FE FF` |
| 短按 (down→up) | `ButtonClicked` 计数 +1 | `>ENC_BUTTON raw down` → `>ENC_BUTTON raw up` |
| 长按 | Radial 菜单弹出或 `ButtonHolding` | `>ENC_BUTTON hold candidate` |

**PASS** = 至少出现 `RotationChanged` 和 `ButtonClicked`。
**理想** = 长按触发 Windows Radial 菜单。

## 常见问题

### RadialController 初始化失败

- 确保 Windows 版本 ≥ 19041
- 确保项目以 **UWP/WinUI** 方式运行（非 Console）

### 无事件

- ESP32 是否真正连接（查看蓝牙设置 + 固件串口日志 `connected=1`）
- 固件是否打印 `hid=sent`（串口日志应有 `>BLE radial report`）
- ReportRef 是否为 `01 01`
- BLE 设备名和地址是否匹配（避免旧缓存 — 应看到 `ESP32-S3 Radial MVP`）
- Probe 窗口是否在前台并拥有焦点

### 旋转有事件但菜单不弹

- 需要长按按钮（固件持续发送 `button=1`）
- 当前长按仅打印 hold candidate，Windows 根据 hold 时长决定是否弹出菜单

## 文件结构

```
tools/win_radial_probe/
  README.md
  RadialProbe.sln
  RadialProbe/
    RadialProbe.csproj
    App.xaml                 # Application entry
    App.xaml.cs
    MainWindow.xaml          # Window shell
    MainWindow.xaml.cs
    MainPage.xaml            # Probe UI
    MainPage.xaml.cs         # RadialController + event handlers
```
