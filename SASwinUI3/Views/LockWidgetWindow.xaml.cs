using SAS.Models;
using SAS.Services;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media.Imaging;
using System.Runtime.InteropServices;
using WinRT.Interop;
using Windows.Graphics;
using Windows.Storage.Streams;

namespace SAS.Views;

public sealed partial class LockWidgetWindow : Window
{
    private static readonly TimeSpan PreviewMinInterval = TimeSpan.FromMilliseconds(100);

    private const int WidgetWidthDip = 240;
    private const int WidgetHeightDip = 224;
    private const int WidgetMarginDip = 10;

    private readonly IRecognitionService _recognitionService;
    private readonly AppLogService _log;
    private int _previewRenderActive;
    private bool _isClosed;
    private PreviewFrame? _pendingPreviewFrame;
    private DateTimeOffset _lastPreviewRenderAt = DateTimeOffset.MinValue;

    public LockWidgetWindow(IRecognitionService recognitionService, AppLogService log)
    {
        InitializeComponent();

        _recognitionService = recognitionService;
        _log = log;

        ConfigureWindow();
        UpdateStatus(_recognitionService.CurrentStatus);

        _recognitionService.StatusChanged += RecognitionService_StatusChanged;
        _recognitionService.UnlockRecognized += RecognitionService_UnlockRecognized;
        _recognitionService.PreviewFrameAvailable += RecognitionService_PreviewFrameAvailable;
        Closed += LockWidgetWindow_Closed;
    }

    private void ConfigureWindow()
    {
        Title = "SAS Locked";
        AppWindow.Title = "SAS Locked";

        var scale = GetCurrentWindowScale();
        var width = ToPixels(WidgetWidthDip, scale);
        var height = ToPixels(WidgetHeightDip, scale);
        var margin = ToPixels(WidgetMarginDip, scale);
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
        var x = workArea.X + Math.Max(margin, workArea.Width - width - margin);
        var y = workArea.Y + Math.Max(margin, workArea.Height - height - margin);
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

    private void RecognitionService_StatusChanged(object? sender, RecognitionStatus status)
    {
        DispatcherQueue.TryEnqueue(() => UpdateStatus(status));
    }

    private void RecognitionService_UnlockRecognized(object? sender, RecognitionUnlockEvent e)
    {
        DispatcherQueue.TryEnqueue(() => StatusTextBlock.Text = "Authorized face matched. Unlocking...");
    }

    private void RecognitionService_PreviewFrameAvailable(object? sender, PreviewFrame frame)
    {
        _pendingPreviewFrame = frame;
        if (Interlocked.Exchange(ref _previewRenderActive, 1) != 0)
        {
            return;
        }

        DispatcherQueue.TryEnqueue(async () => await DrainPreviewFramesAsync());
    }

    private async Task DrainPreviewFramesAsync()
    {
        try
        {
            while (_pendingPreviewFrame is { } frame)
            {
                _pendingPreviewFrame = null;
                if (_isClosed)
                {
                    return;
                }

                var wait = PreviewMinInterval - (DateTimeOffset.Now - _lastPreviewRenderAt);
                if (wait > TimeSpan.Zero)
                {
                    await Task.Delay(wait);
                }

                await UpdatePreviewAsync(frame);
            }
        }
        finally
        {
            Interlocked.Exchange(ref _previewRenderActive, 0);
            if (!_isClosed &&
                _pendingPreviewFrame is not null &&
                Interlocked.Exchange(ref _previewRenderActive, 1) == 0)
            {
                DispatcherQueue.TryEnqueue(async () => await DrainPreviewFramesAsync());
            }
        }
    }

    private async Task UpdatePreviewAsync(PreviewFrame frame)
    {
        if (_isClosed)
        {
            return;
        }

        try
        {
            using var stream = new InMemoryRandomAccessStream();
            using var writer = new DataWriter(stream);
            writer.WriteBytes(frame.JpegBytes);
            await writer.StoreAsync();
            await writer.FlushAsync();
            writer.DetachStream();

            stream.Seek(0);
            var bitmap = new BitmapImage();
            await bitmap.SetSourceAsync(stream);

            PreviewImage.Source = bitmap;
            PreviewPlaceholder.Visibility = Visibility.Collapsed;
            _lastPreviewRenderAt = DateTimeOffset.Now;
        }
        catch (Exception ex)
        {
            PreviewPlaceholder.Text = "Preview unavailable";
            PreviewPlaceholder.Visibility = Visibility.Visible;
            _log.Write($"Lock widget preview failed: {ex.Message}");
        }
    }

    private void UpdateStatus(RecognitionStatus status)
    {
        if (_isClosed)
        {
            return;
        }

        var hasRecentPreview = status.LastFrameAt is not null &&
            DateTimeOffset.Now - status.LastFrameAt.Value < TimeSpan.FromSeconds(10);
        if (status.StreamHealthy && hasRecentPreview)
        {
            StatusTextBlock.Text = "Scan your face to unlock";
            return;
        }

        if (status.StreamHealthy && status.LastFrameAt is null)
        {
            StatusTextBlock.Text = "Waiting for camera preview...";
            PreviewPlaceholder.Text = "Resuming camera";
            PreviewPlaceholder.Visibility = Visibility.Visible;
            return;
        }

        StatusTextBlock.Text = string.IsNullOrWhiteSpace(status.LastError)
            ? $"Camera state: {status.ConnectionState}"
            : status.LastError;

        if (status.ConnectionState.Contains("disconnect", StringComparison.OrdinalIgnoreCase)
            || status.ConnectionState.Contains("reconnect", StringComparison.OrdinalIgnoreCase))
        {
            PreviewImage.Source = null;
            PreviewPlaceholder.Text = "Camera disconnected";
            PreviewPlaceholder.Visibility = Visibility.Visible;
            return;
        }

        if (PreviewImage.Source is null)
        {
            PreviewPlaceholder.Text = string.IsNullOrWhiteSpace(status.LastError)
                ? "Waiting for camera"
                : "Camera unavailable";
            PreviewPlaceholder.Visibility = Visibility.Visible;
        }
    }

    private void LockWidgetWindow_Closed(object sender, WindowEventArgs args)
    {
        _isClosed = true;
        _recognitionService.StatusChanged -= RecognitionService_StatusChanged;
        _recognitionService.UnlockRecognized -= RecognitionService_UnlockRecognized;
        _recognitionService.PreviewFrameAvailable -= RecognitionService_PreviewFrameAvailable;
    }
}





