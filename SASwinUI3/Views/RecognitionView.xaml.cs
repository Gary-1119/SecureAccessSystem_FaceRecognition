using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using System.Collections;

namespace SAS.Views;

public sealed partial class RecognitionView : UserControl
{
    public event RoutedEventHandler? RegisterFaceRequested;
    public event RoutedEventHandler? DeleteFaceRequested;
    public event RoutedEventHandler? OpenCameraRequested;
    public event RoutedEventHandler? CloseCameraRequested;
    public event TextChangedEventHandler? UserSearchChanged;
    public event EventHandler<FaceUserListItem>? UserSelected;

    public RecognitionView()
    {
        InitializeComponent();
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

    public void SetUsersSubtitle(string subtitle)
    {
        FaceUsersSubtitleTextBlock.Text = subtitle;
    }

    public void SetPreviewImage(BitmapImage image)
    {
        CameraPreviewImage.Source = image;
        CameraPreviewPlaceholder.Visibility = Visibility.Collapsed;
    }

    public void ClearPreview(string message)
    {
        CameraPreviewImage.Source = null;
        ShowPreviewMessage(message);
    }

    public void ShowPreviewMessage(string message)
    {
        CameraPreviewPlaceholder.Text = message;
        CameraPreviewPlaceholder.Visibility = Visibility.Visible;
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










