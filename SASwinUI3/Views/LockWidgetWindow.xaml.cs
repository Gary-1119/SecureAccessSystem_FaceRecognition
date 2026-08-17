using SAS.Models;
using SAS.Services;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
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
    private RecognitionStatus _latestStatus;
    private double _previewPixelWidth;
    private double _previewPixelHeight;

    public LockWidgetWindow(IRecognitionService recognitionService, AppLogService log)
    {
        InitializeComponent();

        _recognitionService = recognitionService;
        _log = log;
        _latestStatus = _recognitionService.CurrentStatus;

        ConfigureWindow();
        UpdateStatus(_latestStatus);

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
            _previewPixelWidth = bitmap.PixelWidth;
            _previewPixelHeight = bitmap.PixelHeight;
            PreviewPlaceholder.Visibility = Visibility.Collapsed;
            _lastPreviewRenderAt = DateTimeOffset.Now;
            UpdateFaceOverlay(_latestStatus);
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
            DateTimeOffset.Now - status.LastFrameAt.Value < TimeSpan.FromSeconds(60);
        _latestStatus = status;
        UpdateFaceOverlay(status);
        if (status.StreamHealthy && hasRecentPreview)
        {
            StatusTextBlock.Text = "Scan your face to unlock";
            return;
        }

        if (status.StreamHealthy || (status.IsRunning && hasRecentPreview))
        {
            StatusTextBlock.Text = status.StreamHealthy
                ? "Waiting for camera preview..."
                : "Camera feed recovering";
            if (PreviewImage.Source is null)
            {
                PreviewPlaceholder.Text = "Resuming camera";
                PreviewPlaceholder.Visibility = Visibility.Visible;
            }
            return;
        }

        StatusTextBlock.Text = string.IsNullOrWhiteSpace(status.LastError)
            ? $"Camera state: {status.ConnectionState}"
            : status.LastError;

        if (status.ConnectionState.Contains("disconnect", StringComparison.OrdinalIgnoreCase)
            || status.ConnectionState.Contains("reconnect", StringComparison.OrdinalIgnoreCase))
        {
            if (PreviewImage.Source is null)
            {
                PreviewPlaceholder.Text = "Camera disconnected";
                PreviewPlaceholder.Visibility = Visibility.Visible;
            }
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

    private void UpdateFaceOverlay(RecognitionStatus status)
    {
        if (_isClosed || status.FaceBox is null || _previewPixelWidth <= 0 || _previewPixelHeight <= 0 ||
            PreviewImage.ActualWidth <= 0 || PreviewImage.ActualHeight <= 0 || PreviewImage.Source is null)
        {
            FaceOverlayBorder.Visibility = Visibility.Collapsed;
            FaceOverlayLabelBorder.Visibility = Visibility.Collapsed;
            return;
        }

        var faceBox = status.FaceBox;
        var viewWidth = PreviewImage.ActualWidth;
        var viewHeight = PreviewImage.ActualHeight;
        var imageAspect = _previewPixelWidth / _previewPixelHeight;
        var viewAspect = viewWidth / viewHeight;
        var drawnWidth = viewWidth;
        var drawnHeight = viewHeight;
        var offsetX = 0d;
        var offsetY = 0d;

        if (viewAspect > imageAspect)
        {
            drawnWidth = viewHeight * imageAspect;
            offsetX = (viewWidth - drawnWidth) / 2d;
        }
        else
        {
            drawnHeight = viewWidth / imageAspect;
            offsetY = (viewHeight - drawnHeight) / 2d;
        }

        var left = offsetX + faceBox.Left * drawnWidth;
        var top = offsetY + faceBox.Top * drawnHeight;
        var width = Math.Max(18, faceBox.Width * drawnWidth);
        var height = Math.Max(18, faceBox.Height * drawnHeight);
        var recognized = !string.IsNullOrWhiteSpace(status.LastMatchedEmployeeId) && status.LastLivenessPassed != false;
        var brush = recognized
            ? new SolidColorBrush(ColorHelper.FromArgb(255, 34, 160, 107))
            : new SolidColorBrush(ColorHelper.FromArgb(255, 217, 45, 32));

        FaceOverlayBorder.BorderBrush = brush;
        FaceOverlayLabelBorder.Background = brush;
        FaceOverlayBorder.Width = width;
        FaceOverlayBorder.Height = height;
        Canvas.SetLeft(FaceOverlayBorder, left);
        Canvas.SetTop(FaceOverlayBorder, top);
        FaceOverlayBorder.Visibility = Visibility.Visible;

        FaceOverlayLabelTextBlock.Text = BuildFaceOverlayLabel(status, recognized);
        FaceOverlayLabelBorder.MaxWidth = Math.Max(120, Math.Min(viewWidth - 8, width * 3.2));
        Canvas.SetLeft(FaceOverlayLabelBorder, Math.Clamp(left, 4, Math.Max(4, viewWidth - FaceOverlayLabelBorder.MaxWidth - 4)));
        Canvas.SetTop(FaceOverlayLabelBorder, Math.Max(4, top - 22));
        FaceOverlayLabelBorder.Visibility = Visibility.Visible;
    }

    private static string BuildFaceOverlayLabel(RecognitionStatus status, bool recognized)
    {
        if (status.LastLivenessPassed == false)
        {
            return status.LastLivenessScore is null
                ? status.LastLivenessMessage ?? "Live check pending"
                : $"{status.LastLivenessMessage ?? "Live check pending"} | Blink {status.LastLivenessScore.Value:0.0}%";
        }

        if (recognized)
        {
            var liveText = status.LastLivenessScore is null ? "" : $" | Blink {status.LastLivenessScore.Value:0.0}%";
            return $"{status.LastMatchedName} | {status.LastMatchedEmployeeId} | Face {(status.LastConfidence ?? 0):0.0}%{liveText}";
        }

        return status.LastConfidence is null ? "Unknown" : $"Unknown | Face {status.LastConfidence.Value:0.0}%";
    }

    private void LockWidgetWindow_Closed(object sender, WindowEventArgs args)
    {
        _isClosed = true;
        _recognitionService.StatusChanged -= RecognitionService_StatusChanged;
        _recognitionService.UnlockRecognized -= RecognitionService_UnlockRecognized;
        _recognitionService.PreviewFrameAvailable -= RecognitionService_PreviewFrameAvailable;
    }
}





