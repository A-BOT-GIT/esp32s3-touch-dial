using System;
using System.Collections.ObjectModel;
using System.Linq;
using Windows.ApplicationModel.DataTransfer;
using Windows.UI.Core;
using Windows.UI.Input;
using Windows.UI.Xaml;
using Windows.UI.Xaml.Controls;

namespace RadialProbe
{
    public sealed partial class MainPage : Page
    {
        private RadialController radialController;
        private RadialControllerConfiguration radialConfig;
        private RadialControllerMenuItem probeItem;
        private ObservableCollection<string> events = new ObservableCollection<string>();
        private double rotationTotal = 0;
        private int buttonClicks = 0;

        public MainPage()
        {
            this.InitializeComponent();
            EventList.ItemsSource = events;
            this.Loaded += OnLoaded;
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            try
            {
                InitRadialController();
            }
            catch (Exception ex)
            {
                Log($"[ERROR] Init: {ex.Message}");
                StatusText.Text = "ERROR: " + ex.Message;
            }
        }

        private void InitRadialController()
        {
            radialController = RadialController.CreateForCurrentView();
            radialController.RotationResolutionInDegrees = 1;

            radialConfig = RadialControllerConfiguration.GetForCurrentView();

            // Diagnostic mode: clear system defaults, keep only ESP32 Probe
            radialConfig.SetDefaultMenuItems(
                new RadialControllerSystemMenuItemKind[] { });

            try
            {
                radialController.Menu.Items.Clear();
                Log("Menu.Items.Clear OK");
            }
            catch (Exception ex)
            {
                Log("Menu.Items.Clear failed: " + ex.Message);
            }

            probeItem = RadialControllerMenuItem.CreateFromFontGlyph(
                "ESP32 Probe",
                "",
                "Segoe MDL2 Assets");

            probeItem.Invoked += OnProbeMenuInvoked;
            radialController.Menu.Items.Add(probeItem);

            radialController.RotationChanged += OnRotationChanged;
            radialController.ButtonClicked += OnButtonClicked;
            radialController.ControlAcquired += OnControlAcquired;
            radialController.ControlLost += OnControlLost;

            // Optional events (compile-safe try)
            try { radialController.ButtonPressed += OnButtonPressed; }
            catch { Log("ButtonPressed not supported by SDK"); }
            try { radialController.ButtonReleased += OnButtonReleased; }
            catch { Log("ButtonReleased not supported by SDK"); }
            try { radialController.ButtonHolding += OnButtonHolding; }
            catch { Log("ButtonHolding not supported by SDK"); }

            Log("RadialController diagnostic mode initialized");
            Log("Default system menu items cleared");
            Log("Custom menu item added: ESP32 Probe");

            StatusText.Text = "Ready — long press, select ESP32 Probe";
            MenuText.Text = "Menu: ESP32 Probe installed";
        }

        #region RadialController Events

        private async void OnRotationChanged(RadialController sender,
                                             RadialControllerRotationChangedEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                double delta = args.RotationDeltaInDegrees;
                rotationTotal += delta;
                RotationText.Text = $"Rotation: {rotationTotal:F2}";
                Log($"RotationChanged delta={delta:F2} total={rotationTotal:F2}");
            });
        }

        private async void OnButtonClicked(RadialController sender,
                                           RadialControllerButtonClickedEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                buttonClicks++;
                ButtonText.Text = $"Clicks: {buttonClicks}";
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

        private async void OnProbeMenuInvoked(RadialControllerMenuItem sender, object args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                MenuText.Text = "Menu: ESP32 Probe selected";
                Log("MenuItem Invoked: ESP32 Probe");
            });
        }

        private async void OnButtonPressed(RadialController sender,
                                           RadialControllerButtonPressedEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                Log("ButtonPressed");
            });
        }

        private async void OnButtonReleased(RadialController sender,
                                            RadialControllerButtonReleasedEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                Log("ButtonReleased");
            });
        }

        private async void OnButtonHolding(RadialController sender,
                                           RadialControllerButtonHoldingEventArgs args)
        {
            await Dispatcher.RunAsync(CoreDispatcherPriority.Normal, () =>
            {
                Log("ButtonHolding");
            });
        }

        #endregion

        #region UI

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
            RotationText.Text = "Rotation: 0.00";
            ButtonText.Text = "Clicks: 0";
            Log("--- Cleared ---");
        }

        private void OnCopyClicked(object sender, RoutedEventArgs e)
        {
            string text = string.Join("\n", events.Reverse());
            var dp = new DataPackage();
            dp.SetText(text);
            Clipboard.SetContent(dp);
            Log("--- Copied to clipboard ---");
        }

        #endregion
    }
}
