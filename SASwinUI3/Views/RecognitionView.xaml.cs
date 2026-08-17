using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using System.Collections;
using SAS.Models;

namespace SAS.Views;

public sealed partial class RecognitionView : UserControl
{
    public event RoutedEventHandler? RegisterFaceRequested;
    public event RoutedEventHandler? DeleteFaceRequested;
    public event RoutedEventHandler? OpenCameraRequested;
    public event RoutedEventHandler? CloseCameraRequested;
    public event TextChangedEventHandler? UserSearchChanged;
    public event EventHandler<FaceUserListItem>? UserSelected;
    private RecognitionFaceBox? _faceBox;
    private bool _faceBoxRecognized;
    private double _previewPixelWidth;
    private double _previewPixelHeight;

    public RecognitionView()
    {
        InitializeComponent();
        CameraPreviewImage.SizeChanged += (_, _) => UpdateFaceOverlay();
    }

    public string RegisterName
    {
        get => RegisterNameTextBox.Text;
        set => RegisterNameTextBox.Text = value;
    }

    public string RegisterEmployeeId
    {
        get => RegisterEmployeeIdTextBox.Text;
        set => RegisterEmployeeIdTextBox.Text = value;
    }

    public string UserSearchText => UserSearchTextBox.Text?.Trim() ?? "";

    public bool HasPreviewImage => CameraPreviewImage.Source is not null;

    public void SetLogItemsSource(IEnumerable items)
    {
        FaceLogListView.ItemsSource = items;
    }

    public void SetUsersItemsSource(IEnumerable items)
    {
        UsersListView.ItemsSource = items;
    }

    public void SetCameraState(string state)
    {
        CameraStateTextBlock.Text = state;
    }

    public void SetRecognitionStatus(
        string result,
        string name,
        string employeeId,
        double? confidence,
        RecognitionFaceBox? faceBox,
        double? livenessScore = null,
        bool? livenessPassed = null,
        string? livenessMessage = null)
    {
        SetFaceOverlay(result, name, employeeId, confidence, faceBox, livenessScore, livenessPassed, livenessMessage);
    }

    public void SetUsersSubtitle(string subtitle)
    {
        FaceUsersSubtitleTextBlock.Text = subtitle;
    }

    public void SetPreviewImage(BitmapImage image)
    {
        CameraPreviewImage.Source = image;
        _previewPixelWidth = image.PixelWidth;
        _previewPixelHeight = image.PixelHeight;
        CameraPreviewPlaceholder.Visibility = Visibility.Collapsed;
        UpdateFaceOverlay();
    }

    public void ClearPreview(string message)
    {
        CameraPreviewImage.Source = null;
        _faceBox = null;
        FaceOverlayBorder.Visibility = Visibility.Collapsed;
        FaceOverlayLabelBorder.Visibility = Visibility.Collapsed;
        ShowPreviewMessage(message);
    }

    public void ShowPreviewMessage(string message)
    {
        CameraPreviewPlaceholder.Text = message;
        CameraPreviewPlaceholder.Visibility = Visibility.Visible;
    }

    private void SetFaceOverlay(
        string result,
        string name,
        string employeeId,
        double? confidence,
        RecognitionFaceBox? faceBox,
        double? livenessScore,
        bool? livenessPassed,
        string? livenessMessage)
    {
        _faceBox = faceBox;
        _faceBoxRecognized = string.Equals(result, "Recognized", StringComparison.OrdinalIgnoreCase) && livenessPassed != false;

        if (faceBox is null)
        {
            FaceOverlayBorder.Visibility = Visibility.Collapsed;
            FaceOverlayLabelBorder.Visibility = Visibility.Collapsed;
            return;
        }

        var brush = _faceBoxRecognized
            ? (Brush)Application.Current.Resources["SystemFillColorSuccessBrush"]
            : new SolidColorBrush(Microsoft.UI.Colors.Firebrick);
        FaceOverlayBorder.BorderBrush = brush;
        FaceOverlayLabelBorder.Background = brush;

        FaceOverlayLabelTextBlock.Text = BuildFaceOverlayLabel(
            result,
            name,
            employeeId,
            confidence,
            livenessScore,
            livenessPassed,
            livenessMessage);
        UpdateFaceOverlay();
    }

    private static string BuildFaceOverlayLabel(
        string result,
        string name,
        string employeeId,
        double? confidence,
        double? livenessScore,
        bool? livenessPassed,
        string? livenessMessage)
    {
        if (livenessPassed == false)
        {
            return livenessScore is null
                ? livenessMessage ?? "Live check pending"
                : $"{livenessMessage ?? "Live check pending"} | Blink {livenessScore.Value:0.0}%";
        }

        if (string.Equals(result, "Recognized", StringComparison.OrdinalIgnoreCase))
        {
            var liveText = livenessScore is null ? "" : $" | Blink {livenessScore.Value:0.0}%";
            return $"{name} | {employeeId} | Face {(confidence ?? 0):0.0}%{liveText}";
        }

        return confidence is null ? "Unknown" : $"Unknown | Face {confidence.Value:0.0}%";
    }

    private void UpdateFaceOverlay()
    {
        if (_faceBox is null || _previewPixelWidth <= 0 || _previewPixelHeight <= 0 ||
            CameraPreviewImage.ActualWidth <= 0 || CameraPreviewImage.ActualHeight <= 0)
        {
            return;
        }

        var imageAspect = _previewPixelWidth / _previewPixelHeight;
        var viewWidth = CameraPreviewImage.ActualWidth;
        var viewHeight = CameraPreviewImage.ActualHeight;
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

        var left = offsetX + _faceBox.Left * drawnWidth;
        var top = offsetY + _faceBox.Top * drawnHeight;
        var width = Math.Max(24, _faceBox.Width * drawnWidth);
        var height = Math.Max(24, _faceBox.Height * drawnHeight);

        FaceOverlayBorder.Width = width;
        FaceOverlayBorder.Height = height;
        Canvas.SetLeft(FaceOverlayBorder, left);
        Canvas.SetTop(FaceOverlayBorder, top);
        FaceOverlayBorder.Visibility = Visibility.Visible;

        FaceOverlayLabelBorder.MaxWidth = Math.Max(180, Math.Min(viewWidth - 8, width * 2.6));
        Canvas.SetLeft(FaceOverlayLabelBorder, Math.Clamp(left, 4, Math.Max(4, viewWidth - FaceOverlayLabelBorder.MaxWidth - 4)));
        Canvas.SetTop(FaceOverlayLabelBorder, Math.Max(0, top - 30));
        FaceOverlayLabelBorder.Visibility = Visibility.Visible;
    }

    public void ApplyResponsiveLayout(double availableWidth, double availableHeight)
    {
        if (availableWidth <= 0 || availableHeight <= 0)
        {
            return;
        }

        var stacked = availableWidth < 900;
        if (stacked)
        {
            CameraColumn.Width = new GridLength(1, GridUnitType.Star);
            ManagementColumn.Width = new GridLength(0);
            CameraLogPanel.SetValue(Grid.ColumnProperty, 0);
            CameraLogPanel.SetValue(Grid.RowProperty, 0);
            ManagementPanel.SetValue(Grid.ColumnProperty, 0);
            ManagementPanel.SetValue(Grid.RowProperty, 1);
        }
        else
        {
            CameraColumn.Width = new GridLength(1, GridUnitType.Star);
            ManagementColumn.Width = new GridLength(330);
            CameraLogPanel.SetValue(Grid.ColumnProperty, 0);
            CameraLogPanel.SetValue(Grid.RowProperty, 0);
            ManagementPanel.SetValue(Grid.ColumnProperty, 1);
            ManagementPanel.SetValue(Grid.RowProperty, 0);
        }

        ApplyCameraControlLayout(availableWidth < 1280);

        var cameraHeight = stacked
            ? Math.Clamp(availableHeight * 0.55, 440, 620)
            : availableHeight >= 960 ? 640 : Math.Max(520, availableHeight - 320);
        var logHeight = stacked
            ? 240
            : availableHeight >= 960 ? 330 : 280;
        CameraRow.Height = new GridLength(cameraHeight);
        LogRow.Height = new GridLength(logHeight);
        AuthorizedUsersCard.Height = stacked ? 330 : cameraHeight + 16 + logHeight;
    }



    private void ApplyCameraControlLayout(bool stacked)
    {
        if (stacked)
        {
            CameraNameColumn.Width = new GridLength(1, GridUnitType.Star);
            CameraIdColumn.Width = new GridLength(0);
            CameraCommandColumn.Width = new GridLength(0);

            RegisterNameTextBox.SetValue(Grid.ColumnProperty, 0);
            RegisterNameTextBox.SetValue(Grid.ColumnSpanProperty, 3);
            RegisterNameTextBox.SetValue(Grid.RowProperty, 0);

            RegisterEmployeeIdTextBox.SetValue(Grid.ColumnProperty, 0);
            RegisterEmployeeIdTextBox.SetValue(Grid.ColumnSpanProperty, 3);
            RegisterEmployeeIdTextBox.SetValue(Grid.RowProperty, 1);

            ControlCommandBar.SetValue(Grid.ColumnProperty, 0);
            ControlCommandBar.SetValue(Grid.ColumnSpanProperty, 3);
            ControlCommandBar.SetValue(Grid.RowProperty, 2);
            ControlCommandBar.DefaultLabelPosition = CommandBarDefaultLabelPosition.Bottom;
            ControlCommandBar.HorizontalAlignment = HorizontalAlignment.Right;
        }
        else
        {
            CameraNameColumn.Width = new GridLength(1, GridUnitType.Star);
            CameraIdColumn.Width = new GridLength(1, GridUnitType.Star);
            CameraCommandColumn.Width = GridLength.Auto;

            RegisterNameTextBox.SetValue(Grid.ColumnProperty, 0);
            RegisterNameTextBox.SetValue(Grid.ColumnSpanProperty, 1);
            RegisterNameTextBox.SetValue(Grid.RowProperty, 0);

            RegisterEmployeeIdTextBox.SetValue(Grid.ColumnProperty, 1);
            RegisterEmployeeIdTextBox.SetValue(Grid.ColumnSpanProperty, 1);
            RegisterEmployeeIdTextBox.SetValue(Grid.RowProperty, 0);

            ControlCommandBar.SetValue(Grid.ColumnProperty, 2);
            ControlCommandBar.SetValue(Grid.ColumnSpanProperty, 1);
            ControlCommandBar.SetValue(Grid.RowProperty, 0);
            ControlCommandBar.DefaultLabelPosition = CommandBarDefaultLabelPosition.Bottom;
            ControlCommandBar.HorizontalAlignment = HorizontalAlignment.Right;
        }
    }
    private void RegisterFaceButton_Click(object sender, RoutedEventArgs e)
    {
        RegisterFaceRequested?.Invoke(sender, e);
    }

    private void DeleteFaceButton_Click(object sender, RoutedEventArgs e)
    {
        DeleteFaceRequested?.Invoke(sender, e);
    }

    private void OpenCameraButton_Click(object sender, RoutedEventArgs e)
    {
        OpenCameraRequested?.Invoke(sender, e);
    }

    private void CloseCameraButton_Click(object sender, RoutedEventArgs e)
    {
        CloseCameraRequested?.Invoke(sender, e);
    }

    private void UserSearchTextBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        UserSearchChanged?.Invoke(sender, e);
    }

    private void UsersListView_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (UsersListView.SelectedItem is not FaceUserListItem user)
        {
            return;
        }

        RegisterName = user.DisplayName;
        RegisterEmployeeId = user.EmployeeId;
        UserSelected?.Invoke(this, user);
    }

    private void UserActionsButton_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not Button button || button.Tag is not FaceUserListItem user)
        {
            return;
        }

        RegisterName = user.DisplayName;
        RegisterEmployeeId = user.EmployeeId;

        var sampleCountItem = new MenuFlyoutItem
        {
            Text = $"{user.SampleCount} face sample{(user.SampleCount == 1 ? "" : "s")}",
            IsEnabled = false
        };

        var captureItem = new MenuFlyoutItem
        {
            Text = "Capture",
            Icon = new SymbolIcon(Symbol.Camera)
        };
        captureItem.Click += (_, args) => RegisterFaceRequested?.Invoke(captureItem, args);

        var deleteItem = new MenuFlyoutItem
        {
            Text = "Delete",
            Icon = new SymbolIcon(Symbol.Delete),
            Foreground = new SolidColorBrush(Microsoft.UI.Colors.Firebrick)
        };
        deleteItem.Click += (_, args) => DeleteFaceRequested?.Invoke(deleteItem, args);

        var flyout = new MenuFlyout();
        flyout.Items.Add(sampleCountItem);
        flyout.Items.Add(new MenuFlyoutSeparator());
        flyout.Items.Add(captureItem);
        flyout.Items.Add(deleteItem);
        flyout.ShowAt(button);
    }
}

public sealed record FaceUserListItem(string EmployeeId, string DisplayName, int SampleCount);










