using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using System.Runtime.InteropServices;
using Windows.Graphics;
using WinRT.Interop;

namespace SAS.Views;

public sealed partial class PiReconnectWindow : Window
{
    private const int WindowWidthDip = 420;
    private const int WindowHeightDip = 300;

    public event EventHandler? RetryRequested;
    public event EventHandler? ChangeHostnameRequested;
    public event EventHandler? DismissRequested;
    public bool IsConnectedState { get; private set; }

    public PiReconnectWindow(string hostname, bool locked)
    {
        InitializeComponent();
        ConfigureWindow();
        ShowDisconnected(hostname, "", locked);
    }

    public void ShowDisconnected(string hostname, string error, bool locked)
    {
        IsConnectedState = false;
        var alreadyOwned = IsAlreadyConnectedByAnotherSas(error);
        TitleTextBlock.Text = alreadyOwned ? "Pi already in use" : "Pi disconnected";
        HostTextBlock.Text = alreadyOwned
            ? string.IsNullOrWhiteSpace(hostname)
                ? "Another SAS device is currently connected."
                : $"\"{hostname}\" is currently connected with another SAS device."
            : string.IsNullOrWhiteSpace(hostname)
                ? "Please restart the Pi."
                : $"Please restart \"{hostname}\".";
        MessageTextBlock.Text = alreadyOwned
            ? "Only one SAS workstation can own a Pi at a time. Close or disconnect the current SAS connection, then retry."
            : locked
                ? "SAS is locked and waiting for the camera connection to come back. The unlock camera will resume automatically after reconnect."
                : "SAS cannot reach the Pi camera. Keep this window open and restart or reconnect the Pi. The camera preview will resume automatically.";
        StatusTextBlock.Text = string.IsNullOrWhiteSpace(error)
            ? alreadyOwned ? "Waiting for the current SAS connection to be released..." : "Trying to reconnect..."
            : error;
        ReconnectProgressRing.IsActive = true;
        ReconnectProgressRing.Visibility = Visibility.Visible;
        StateIcon.Glyph = "\uE783";
        StateIcon.Foreground = new SolidColorBrush(ColorHelper.FromArgb(255, 157, 93, 0));
        RetryButton.Visibility = Visibility.Visible;
        ChangeHostnameButton.Visibility = Visibility.Visible;
        ChangeHostnameButtonText.Text = locked ? "Admin change hostname" : "Change hostname";
        DismissButton.Content = "Dismiss";
        DismissButton.Visibility = locked ? Visibility.Collapsed : Visibility.Visible;
    }

    private static bool IsAlreadyConnectedByAnotherSas(string message)
    {
        return message.Contains("already connected", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("another SAS", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("another SAS device", StringComparison.OrdinalIgnoreCase);
    }

    public void ShowConnected(bool locked)
    {
        IsConnectedState = true;
        TitleTextBlock.Text = "Pi connected";
        HostTextBlock.Text = "Camera connection restored.";
        MessageTextBlock.Text = locked
            ? "SAS is resuming the locked camera preview. You can scan your face to unlock."
            : "SAS is resuming the camera preview.";
        StatusTextBlock.Text = "Connected. Resuming camera preview...";
        ReconnectProgressRing.IsActive = false;
        ReconnectProgressRing.Visibility = Visibility.Collapsed;
        StateIcon.Glyph = "\uE73E";
        StateIcon.Foreground = new SolidColorBrush(ColorHelper.FromArgb(255, 16, 124, 16));
        RetryButton.Visibility = Visibility.Collapsed;
        ChangeHostnameButton.Visibility = Visibility.Collapsed;
        DismissButton.Content = "Close";
        DismissButton.Visibility = Visibility.Visible;
    }

    private void RetryButton_Click(object sender, RoutedEventArgs e)
    {
        RetryRequested?.Invoke(this, EventArgs.Empty);
    }

    private void ChangeHostnameButton_Click(object sender, RoutedEventArgs e)
    {
        ChangeHostnameRequested?.Invoke(this, EventArgs.Empty);
    }

    private void DismissButton_Click(object sender, RoutedEventArgs e)
    {
        DismissRequested?.Invoke(this, EventArgs.Empty);
    }

    private void ConfigureWindow()
    {
        Title = "SAS Pi Connection";
        AppWindow.Title = "SAS Pi Connection";

        var scale = GetCurrentWindowScale();
        var width = ToPixels(WindowWidthDip, scale);
        var height = ToPixels(WindowHeightDip, scale);
        AppWindow.Resize(new SizeInt32(width, height));

        var iconPath = Path.Combine(AppContext.BaseDirectory, "Assets", "SasLogo.ico");
        if (File.Exists(iconPath))
        {
            AppWindow.SetIcon(iconPath);
        }

        if (AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.IsAlwaysOnTop = true;
            presenter.IsResizable = false;
            presenter.IsMaximizable = false;
            presenter.IsMinimizable = false;
            presenter.SetBorderAndTitleBar(false, false);
        }

        var workArea = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Nearest).WorkArea;
        var x = workArea.X + Math.Max(0, (workArea.Width - width) / 2);
        var y = workArea.Y + Math.Max(0, (workArea.Height - height) / 2);
        AppWindow.Move(new PointInt32(x, y));
    }

    private double GetCurrentWindowScale()
    {
        var hwnd = WindowNative.GetWindowHandle(this);
        if (hwnd == IntPtr.Zero)
        {
            return 1.0;
        }

        var dpi = GetDpiForWindow(hwnd);
        return dpi > 0 ? dpi / 96.0 : 1.0;
    }

    private static int ToPixels(int dips, double scale)
    {
        return Math.Max(1, (int)Math.Round(dips * scale));
    }

    [DllImport("User32.dll")]
    private static extern uint GetDpiForWindow(IntPtr hwnd);
}
