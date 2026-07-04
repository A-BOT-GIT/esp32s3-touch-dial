# 13 Windows Radial Probe 实现方案

版本：v1.2

## 1. 目标

创建一个最小 Windows 测试程序，用来验证：

```text
ESP32 是否被 Windows RadialController API 消费。
```

这个工具不是普通 HID viewer，而是直接验证 Windows wheel / radial controller 输入路径。

---

## 2. 推荐目录

```text
tools/win_radial_probe/
  README.md
  RadialProbe.sln
  RadialProbe/
    App.xaml
    App.xaml.cs
    MainPage.xaml
    MainPage.xaml.cs
    RadialProbeLogger.cs
```

---

## 3. UWP / WinUI 选择

优先 UWP，因为 `Windows.UI.Input.RadialController` 是 UWP API 常见入口。

目标 Windows：

```text
Windows 10 1607+，优先用户当前 Windows 10 19041 环境
```

---

## 4. MainPage UI 建议

`MainPage.xaml`：

```xml
<Page
    x:Class="RadialProbe.MainPage"
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

    <Grid Padding="24">
        <StackPanel Spacing="12">
            <TextBlock Text="ESP32 Radial Controller Probe" FontSize="24"/>
            <TextBlock x:Name="StatusText" Text="Waiting for RadialController..." />
            <TextBlock x:Name="RotationText" Text="Rotation total: 0" />
            <TextBlock x:Name="ButtonText" Text="Button clicks: 0" />
            <StackPanel Orientation="Horizontal" Spacing="8">
                <Button Content="Clear" Click="OnClearClicked"/>
                <Button Content="Copy Log" Click="OnCopyLogClicked"/>
            </StackPanel>
            <ListView x:Name="EventList" Height="480"/>
        </StackPanel>
    </Grid>
</Page>
```

---

## 5. C# 事件骨架

`MainPage.xaml.cs` 核心结构：

```csharp
using System;
using System.Collections.ObjectModel;
using Windows.UI.Core;
using Windows.UI.Input;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;

namespace RadialProbe
{
    public sealed partial class MainPage : Page
    {
        private RadialController controller;
        private ObservableCollection<string> events = new ObservableCollection<string>();
        private double rotationTotal = 0;
        private int buttonClicks = 0;

        public MainPage()
        {
            this.InitializeComponent();
            EventList.ItemsSource = events;
            InitRadialController();
        }

        private void InitRadialController()
        {
            controller = RadialController.CreateForCurrentView();

            var menu = controller.Menu;
            menu.Items.Add(RadialControllerMenuItem.CreateFromKnownIcon(
                "ESP32 Probe",
                RadialControllerMenuKnownIcon.Ruler));

            controller.RotationChanged += OnRotationChanged;
            controller.ButtonClicked += OnButtonClicked;
            controller.ControlAcquired += OnControlAcquired;
            controller.ControlLost += OnControlLost;

            Log("RadialController initialized");
        }

        private async void OnRotationChanged(RadialController sender,
                                             RadialControllerRotationChangedEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                rotationTotal += args.RotationDeltaInDegrees;
                RotationText.Text = $"Rotation total: {rotationTotal:F2}";
                Log($"RotationChanged delta={args.RotationDeltaInDegrees:F2} total={rotationTotal:F2}");
            });
        }

        private async void OnButtonClicked(RadialController sender,
                                           RadialControllerButtonClickedEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                buttonClicks++;
                ButtonText.Text = $"Button clicks: {buttonClicks}";
                Log($"ButtonClicked count={buttonClicks}");
            });
        }

        private async void OnControlAcquired(RadialController sender,
                                             RadialControllerControlAcquiredEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                StatusText.Text = "Control acquired";
                Log("ControlAcquired");
            });
        }

        private async void OnControlLost(RadialController sender, object args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                StatusText.Text = "Control lost";
                Log("ControlLost");
            });
        }

        private void Log(string message)
        {
            string line = $"[{DateTime.Now:HH:mm:ss.fff}] {message}";
            events.Insert(0, line);
        }

        private void OnClearClicked(object sender, RoutedEventArgs e)
        {
            events.Clear();
            rotationTotal = 0;
            buttonClicks = 0;
            RotationText.Text = "Rotation total: 0";
            ButtonText.Text = "Button clicks: 0";
        }
    }
}
```

实际事件参数类型需按目标 Windows SDK 编译结果微调。

---

## 6. Probe 验证预期

ESP32 串口：

```text
>BLE radial report len=2 data=02 00 button=0 delta=1 hid=sent
```

Probe：

```text
RotationChanged delta=...
```

ESP32 串口：

```text
>BLE radial report len=2 data=01 00 button=1 delta=0 hid=sent
>BLE radial report len=2 data=00 00 button=0 delta=0 hid=sent
```

Probe：

```text
ButtonClicked count=...
```

---

## 7. 如果 ButtonClicked 不触发

可能原因：

1. Windows RadialController API 不把简单 down/up 映射为 ButtonClicked；
2. 需要 focus 在 probe 窗口；
3. 需要选择 probe 的菜单项；
4. button press/release 太快；
5. BLE report 没有保持 button=1 足够时间；
6. Report Map 不是 Radial Controller。

固件侧可以测试：

```text
按下保持 200ms 再释放
按下保持 1000ms 再释放
```

但不要改成 Consumer Control usage。

---

## 8. 如果 RotationChanged 不触发

按顺序查：

```text
1. 固件是否发送 hid=sent
2. data 是否 02 00 / FE FF
3. ReportRef 是否 01 01
4. Report Map 是否 0x01/0x0E
5. Dial 是否 Relative
6. delta 是否太小
7. Windows 是否连接的是新 identity
8. 是否仍然 Media Dial descriptor
```

---

## 9. README 应写明

Probe README 至少包含：

```text
1. 如何打开 Visual Studio project
2. 需要安装的 Windows SDK
3. 如何连接 ESP32-S3 Radial MVP
4. 如何运行
5. 如何判断 PASS
6. 常见失败现象
```

---

## 10. 可选增强

后续可以加：

```text
导出日志到文件
显示当前 selected tool
显示 RadialController menu item
添加多个 menu items
测试 haptic feedback
Raw HID dump 辅助视图
```
