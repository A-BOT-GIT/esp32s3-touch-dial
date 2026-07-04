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

            // Add menu item via radialController.Menu (not GetForCurrentView)
            var probeItem = RadialControllerMenuItem.CreateFromFontGlyph(
                "ESP32 Probe",
                "",               // MDL2 glyph for ruler/measure
                "Segoe MDL2 Assets");
            radialController.Menu.Items.Add(probeItem);

            // Configure radial controller settings
            RadialControllerConfiguration.GetForCurrentView();

            radialController.RotationChanged += OnRotationChanged;
            radialController.ButtonClicked += OnButtonClicked;
            radialController.ControlAcquired += OnControlAcquired;
            radialController.ControlLost += OnControlLost;

            Log("RadialController initialized — ESP32 Probe menu item added");
            StatusText.Text = "Ready — rotate/press ESP32";
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
