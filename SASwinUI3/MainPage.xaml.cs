using SAS.Models;
using SAS.Controllers;
using SAS.Services;
using SAS.Views;
using SAS.Views.Auth;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Animation;
using Microsoft.UI.Xaml.Navigation;
using System.Collections.ObjectModel;
using Windows.Storage.Streams;
using Windows.Storage.Pickers;
using WinRT.Interop;

namespace SAS;

public sealed partial class MainPage : Page
{
    private static readonly TimeSpan RecognitionPreviewMinInterval = TimeSpan.FromMilliseconds(100);

    private readonly AppSettingsService _settingsService;
    private readonly AppLogService _log;
    private readonly UserAuthService _authService;
    private readonly InactivityService _inactivityService;
    private readonly IRecognitionService _recognitionService;
    private readonly JabilEyeConnectionController _jabilEyeConnectionController;
    private readonly FaceDataController? _faceDataController;
    private readonly LogsController _logsController;
    private readonly SettingsController _settingsController;
    private readonly LockFlowController _lockFlowController;
    private readonly DispatcherQueueTimer _clockTimer;
    private readonly DispatcherQueueTimer _countdownTimer;
    private readonly ObservableCollection<FaceUserListItem> _userRows = [];
    private readonly SemaphoreSlim _dialogSemaphore = new(1, 1);

    private AppSettings _settings;
    private JabilEyeReconnectWindow? _jabilEyeReconnectWindow;
    private LockWidgetWindow? _lockWidgetWindow;
    private CancellationTokenSource? _jabilEyeReconnectCloseCts;
    private bool _suppressJabilEyeReconnectPrompt;
    private bool _isConnectingJabilEye;
    private bool _isEmergencyUnlockPromptOpen;
    private bool _isNavigatingBack;
    private bool _showRecognitionPreview = true;
    private bool _isLoadingSettings;
    private bool _isAutoSavingSettings;
    private int _recognitionPreviewRenderActive;
    private int _recognitionPreviewGeneration;
    private string _currentPageTag = "";
    private readonly Stack<string> _pageBackStack = new();
    private UIElement? _currentPage;
    private PreviewFrame? _pendingRecognitionPreviewFrame;
    private DateTimeOffset _lastRecognitionPreviewRenderAt = DateTimeOffset.MinValue;
    private int _timeLeft;

    public event EventHandler<bool>? BackAvailabilityChanged;

    public bool CanNavigateBack => _pageBackStack.Count > 0;

    public MainPage()
    {
        InitializeComponent();

        _settingsService = new AppSettingsService();
        _inactivityService = new InactivityService();
        _settings = _settingsService.Load();
        _timeLeft = Math.Max(1, _settings.LockTimeoutSeconds);
        ResetInactivityCountdown();

        _log = new AppLogService(action =>
        {
            if (DispatcherQueue.HasThreadAccess)
            {
                action();
                return;
            }

            DispatcherQueue.TryEnqueue(() => action());
        });
        _authService = new UserAuthService();
        _recognitionService = new LocalRtspRecognitionService(_log);
        _jabilEyeConnectionController = new JabilEyeConnectionController(_recognitionService, _log);
        var jabilEyeTransferService = _recognitionService as IJabilEyeTransferService;
        _faceDataController = jabilEyeTransferService is null ? null : new FaceDataController(jabilEyeTransferService, _log);
        _logsController = new LogsController(_log);
        var runtimeLockService = new RuntimeLockService(DispatcherQueue, _log);
        var lockWidgetService = new LockWidgetService(ShowLockWidgetWindow, CloseLockWidgetWindow, _log);
        _lockFlowController = new LockFlowController(runtimeLockService, lockWidgetService, _recognitionService, _log);
        _settingsController = new SettingsController(_settingsService, _authService, _recognitionService, jabilEyeTransferService, _lockFlowController, _log);

        RecognitionPage.SetLogItemsSource(_log.Entries);
        LogsPage.SetSasLogItemsSource(_log.Entries);
        LogsPage.SasLogPath = _log.TodayLogPath;
        LogsPage.DownloadSasLogRequested += DownloadSasLogButton_Click;
        LogsPage.BrowseSasLogFolderRequested += BrowseSasLogFolderButton_Click;
        RecognitionPage.SetUsersItemsSource(_userRows);
        RecognitionPage.RegisterFaceRequested += RegisterFaceButton_Click;
        RecognitionPage.DeleteFaceRequested += DeleteFaceButton_Click;
        RecognitionPage.OpenCameraRequested += OpenCameraButton_Click;
        RecognitionPage.CloseCameraRequested += CloseCameraButton_Click;
        RecognitionPage.UserSearchChanged += UserSearchTextBox_TextChanged;

        _lockFlowController.EmergencyUnlockRequested += (_, _) => EmergencyUnlock();
        _recognitionService.StatusChanged += RecognitionService_StatusChanged;
        _recognitionService.UnlockRecognized += RecognitionService_UnlockRecognized;
        _recognitionService.PreviewFrameAvailable += RecognitionService_PreviewFrameAvailable;

        _clockTimer = DispatcherQueue.CreateTimer();
        _clockTimer.Interval = TimeSpan.FromSeconds(1);
        _clockTimer.Tick += (_, _) => UpdateClock();
        _clockTimer.Start();

        _countdownTimer = DispatcherQueue.CreateTimer();
        _countdownTimer.Interval = TimeSpan.FromSeconds(1);
        _countdownTimer.Tick += (_, _) => UpdateCountdown();
        _countdownTimer.Start();

        LoadSettingsToForm();
        _ = InitializeStartupPiAsync();
        UpdateClock();
        UpdateLockUi();
        RefreshUsers();
        RefreshAdminList();
        ApplyUserPermissions();
        RootNavigationView.SelectedItem = DashboardNavItem;
        UpdatePaneHeader();
        ShowPage(DashboardPage);
        _log.Write("WinUI runtime initialized.");
        _log.WriteAudit("PAGE OPENED", "Dashboard");
        Loaded += MainPage_Loaded;
    }

    private async void MainPage_Loaded(object sender, RoutedEventArgs e)
    {
        Loaded -= MainPage_Loaded;
        await CompleteFreshStartFlowAsync();
    }

    private async Task CompleteFreshStartFlowAsync()
    {
        if (!string.IsNullOrWhiteSpace(_settings.JabilEyeHost))
        {
            MinimizeMainWindow();
            return;
        }

        ActivateMainWindow();
        SettingsCameraStatusTextBlock.Text = "Status: Not configured";
        RecognitionPage.ClearPreview("JabilEye hostname is not configured.");
        _suppressJabilEyeReconnectPrompt = true;

        if (!_authService.HasAdmins || !AppSession.IsAdmin)
        {
            var signedIn = await ShowSignInDialogAsync();
            if (!signedIn || !AppSession.IsAdmin)
            {
                return;
            }
        }

        RootNavigationView.SelectedItem = SettingsNavItem;
        NavigateToPage("Settings", addHistory: false);
        CameraHostTextBox.Focus(FocusState.Programmatic);
    }

    private static void MinimizeMainWindow()
    {
        var window = App.ActiveWindow;
        if (window?.AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.Minimize();
        }
    }

    private async Task InitializeStartupPiAsync()
    {
        await InitializeRecognitionUsersAsync();
    }

    private async Task InitializeRecognitionUsersAsync()
    {
        try
        {
            if (string.IsNullOrWhiteSpace(_settings.JabilEyeHost))
            {
                await _recognitionService.ConfigureAsync(_settings);
                return;
            }

            _showRecognitionPreview = true;
            DispatcherQueue.TryEnqueue(() =>
            {
                SettingsCameraStatusTextBlock.Text = "Status: Connecting...";
                if (!RecognitionPage.HasPreviewImage)
                {
                    RecognitionPage.ClearPreview("Connecting to camera...");
                }
            });

            var result = await _jabilEyeConnectionController.ConnectAsync(
                _settings,
                _ => _settingsController.PushCameraRotationToPiAsync(_settings),
                waitTimeout: TimeSpan.FromSeconds(8));

            DispatcherQueue.TryEnqueue(() =>
            {
                SettingsCameraStatusTextBlock.Text = result.Connected ? "Status: Connected" : "Status: Disconnected";
                SetConnectPiButtonContent(result.Connected ? "Stop Connection" : "Connect");
                if (!result.Connected && !RecognitionPage.HasPreviewImage)
                {
                    RecognitionPage.ClearPreview(result.Message);
                }
            });

            DispatcherQueue.TryEnqueue(RefreshUsers);
        }
        catch (Exception ex)
        {
                _log.Write($"Initial camera users load failed: {ex.Message}");
        }
    }


    protected override void OnNavigatedTo(NavigationEventArgs e)
    {
        SizeChanged += MainPage_SizeChanged;
        ApplyResponsiveLayout(ActualWidth, ActualHeight);
        base.OnNavigatedTo(e);
    }

    private void MainPage_SizeChanged(object sender, SizeChangedEventArgs e)
    {
        ApplyResponsiveLayout(e.NewSize.Width, e.NewSize.Height);
    }

    private void ApplyResponsiveLayout(double width, double height)
    {
        if (height <= 0)
        {
            return;
        }

        var narrow = width < 1500;
        PageContentGrid.Padding = narrow ? new Thickness(24, 12, 20, 12) : new Thickness(70, 28, 70, 28);
        ApplyDashboardResponsiveLayout(width, height);
        RecognitionPage.ApplyResponsiveLayout(width, height);
    }
    private void ApplyDashboardResponsiveLayout(double width, double height)
    {
        var narrow = width < 1500;
        var compactHeight = height < 760;
        var availableHeight = Math.Max(520, height - PageContentGrid.Padding.Top - PageContentGrid.Padding.Bottom - 64);

        if (narrow || compactHeight)
        {
            DashboardPage.RowSpacing = 10;
            DashboardPage.MinHeight = availableHeight;
            DashboardClockStack.Spacing = 0;
            ClockTextBlock.FontSize = compactHeight ? 50 : 56;
            DateTextBlock.FontSize = 12;
            DateTextBlock.CharacterSpacing = 150;

            StatusCard.Padding = new Thickness(22);
            StatusCard.MinHeight = 300;
            StatusCard.Height = Math.Clamp(availableHeight - 94, 350, 430);
            StatusCard.CornerRadius = new CornerRadius(22);

            LockStateTextBlock.FontSize = 26;
            CountdownRingBorder.Width = 118;
            CountdownRingBorder.Height = 118;
            CountdownRingBorder.CornerRadius = new CornerRadius(59);
            CountdownTextBlock.FontSize = 32;
            RemainingTextBlock.FontSize = 10;
            RemainingTextBlock.CharacterSpacing = 110;
            FaceStateTextBlock.FontSize = 16;
            ManualLockButton.Width = 220;
            ManualLockButton.Height = 48;
        }
        else
        {
            DashboardPage.RowSpacing = 16;
            DashboardPage.MinHeight = Math.Max(560, height - PageContentGrid.Padding.Top - PageContentGrid.Padding.Bottom - 96);
            DashboardClockStack.Spacing = 2;
            ClockTextBlock.FontSize = 64;
            DateTextBlock.FontSize = 14;
            DateTextBlock.CharacterSpacing = 190;

            StatusCard.Padding = new Thickness(28);
            StatusCard.MinHeight = 360;
            StatusCard.Height = double.NaN;
            StatusCard.CornerRadius = new CornerRadius(24);

            LockStateTextBlock.FontSize = 30;
            CountdownRingBorder.Width = 142;
            CountdownRingBorder.Height = 142;
            CountdownRingBorder.CornerRadius = new CornerRadius(71);
            CountdownTextBlock.FontSize = 38;
            RemainingTextBlock.FontSize = 11;
            RemainingTextBlock.CharacterSpacing = 130;
            FaceStateTextBlock.FontSize = 18;
            ManualLockButton.Width = 240;
            ManualLockButton.Height = 54;
        }
    }


    private void ApplyUserPermissions()
    {
        var signedIn = AppSession.IsAuthenticated;
        var isAdmin = AppSession.IsAdmin;
        var accountLabel = signedIn
            ? $"{AppSession.Ntid}  {(isAdmin ? "Admin" : "Guest")}"
            : "Guest";

        RecognitionNavItem.IsEnabled = isAdmin;
        FaceDataNavItem.IsEnabled = isAdmin;
        LogsNavItem.IsEnabled = isAdmin;
        SettingsNavItem.IsEnabled = isAdmin;
        AccountNavItem.Visibility = signedIn ? Visibility.Visible : Visibility.Collapsed;
        SignInNavItem.Visibility = signedIn ? Visibility.Collapsed : Visibility.Visible;
        AccountNavItem.Content = accountLabel;
        SignInNavItem.Content = "Sign in";
    }
    private void RefreshAdminList()
    {
        if (AdminListView is null)
        {
            return;
        }

        AdminListView.ItemsSource = _settingsController.AdminNtids;
    }

    private async void AddAdminButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var admin = _settingsController.AddAdmin(AdminNtidTextBox.Text);
            AdminNtidTextBox.Text = "";
            RefreshAdminList();
            await ShowInfoDialogAsync("Admin added", $"{admin.Ntid} can now access management pages.");
        }
        catch (Exception ex)
        {
            await ShowInfoDialogAsync("Admin not added", ex.Message);
        }
    }

    private async void RemoveAdminButton_Click(object sender, RoutedEventArgs e)
    {
        if (sender is not FrameworkElement { Tag: string ntid })
        {
            return;
        }

        if (!await ConfirmAsync("Remove administrator?", $"Remove {ntid} from administrators?"))
        {
            return;
        }

        try
        {
            _settingsController.RemoveAdmin(ntid);
            RefreshAdminList();
            await ShowInfoDialogAsync("Admin removed", $"{ntid} can no longer access management pages.");
        }
        catch (Exception ex)
        {
            await ShowInfoDialogAsync("Admin not removed", ex.Message);
        }
    }

    private void LoadSettingsToForm()
    {
        _isLoadingSettings = true;
        try
        {
            _settings.EnableEmergencyHotkey = true;
            CameraHostTextBox.Text = _settings.CameraHost;
            CameraRtspUserTextBox.Text = string.IsNullOrWhiteSpace(_settings.RtspUser) ? "admin" : _settings.RtspUser;
            CameraRtspPasswordBox.Password = _settings.RtspPassword;
            CameraSourceComboBox.SelectedIndex = 0;
            WebcamIndexComboBox.SelectedIndex = Math.Clamp(_settings.WebcamIndex, 0, 2);
            var canShowServerCredentials = CanShowServerMountCredentials();
            RtspUserTextBox.Text = canShowServerCredentials ? _settings.ServerUsername : "";
            RtspPasswordBox.Password = canShowServerCredentials ? _settings.ServerPassword : "";
            RtspPortTextBox.Text = "8554";
            RtspPathTextBox.Text = _settings.ServerPath;
            LoadLockTimeoutToForm(_settings.LockTimeoutSeconds);
            DisableKeyboardToggle.IsOn = _settings.DisableKeyboardWhenLocked;
            DisableMouseToggle.IsOn = _settings.DisableMouseWhenLocked;
            CameraRotationComboBox.SelectedIndex = _settings.CameraRotation switch
            {
                90 => 1,
                180 => 2,
                270 => 3,
                _ => 0
            };
            UpdateCameraSourceUi();
        }
        finally
        {
            _isLoadingSettings = false;
        }
    }

    private void ReadSettingsFromForm()
    {
        _settings.CameraHost = AppSettings.CleanHost(CameraHostTextBox.Text);
        CameraHostTextBox.Text = _settings.CameraHost;
        _settings.CameraSource = "rtsp";
        _settings.RtspUser = string.IsNullOrWhiteSpace(CameraRtspUserTextBox.Text) ? "admin" : CameraRtspUserTextBox.Text.Trim();
        _settings.RtspPassword = CameraRtspPasswordBox.Password;
        _settings.WebcamIndex = Math.Clamp(WebcamIndexComboBox.SelectedIndex, 0, 2);
        var serverUsername = RtspUserTextBox.Text.Trim();
        var serverPassword = RtspPasswordBox.Password;
        if (!string.IsNullOrWhiteSpace(serverUsername) || !string.IsNullOrWhiteSpace(serverPassword) || CanShowServerMountCredentials())
        {
            _settings.ServerUsername = serverUsername;
            _settings.ServerPassword = serverPassword;
            _settings.ServerCredentialOwnerNtid = AppSession.IsAuthenticated ? AppSession.Ntid.ToUpperInvariant() : "";
        }
        _settings.ApiPort = 5000;
        _settings.ServerPath = FaceDataController.NormalizeServerPath(RtspPathTextBox.Text);
        _settings.RtspPort = 8554;
        _settings.RtspPath = "jabileye-stream";
        _settings.Transport = "tcp";
        _settings.CameraRotation = CameraRotationComboBox.SelectedIndex switch
        {
            1 => 90,
            2 => 180,
            3 => 270,
            _ => 0
        };
        _settings.LockTimeoutSeconds = ReadLockTimeoutSecondsFromForm();
        _settings.DisableKeyboardWhenLocked = DisableKeyboardToggle.IsOn;
        _settings.DisableMouseWhenLocked = DisableMouseToggle.IsOn;
        _settings.DisableUsbWhenLocked = false;
        _settings.EnableEmergencyHotkey = true;
    }

    private bool CanShowServerMountCredentials()
    {
        if (string.IsNullOrWhiteSpace(_settings.ServerUsername) && string.IsNullOrWhiteSpace(_settings.ServerPassword))
        {
            return true;
        }

        if (string.IsNullOrWhiteSpace(_settings.ServerCredentialOwnerNtid))
        {
            return true;
        }

        return AppSession.IsAuthenticated &&
            string.Equals(AppSession.Ntid, _settings.ServerCredentialOwnerNtid, StringComparison.OrdinalIgnoreCase);
    }

    private void UpdateClock()
    {
        ClockTextBlock.Text = DateTime.Now.ToString("HH:mm:ss");
        DateTextBlock.Text = DateTime.Now.ToString("dddd, MMMM d, yyyy").ToUpperInvariant();
    }

    private void UpdateCountdown()
    {
        if (_lockFlowController.IsLocked)
        {
            return;
        }

        _timeLeft = _inactivityService.GetRemainingSeconds(_settings.LockTimeoutSeconds);
        if (_timeLeft == 0)
        {
            LockSystem("Inactivity lock");
            return;
        }

        UpdateCountdownText();
    }

    private void ResetInactivityCountdown()
    {
        _inactivityService.Reset();
        _timeLeft = _inactivityService.GetRemainingSeconds(_settings.LockTimeoutSeconds);
        UpdateCountdownText();
    }

    private void UpdateCountdownText()
    {
        var minutes = _timeLeft / 60;
        var seconds = _timeLeft % 60;
        CountdownTextBlock.Text = $"{minutes:00}:{seconds:00}";
    }

    private void LockSystem(string reason)
    {
        _lockFlowController.Lock(
            _settings,
            reason,
            () => _jabilEyeConnectionController.StartForLockAsync(_settings),
            UpdateLockUi);
    }

    private void UnlockSystem(string reason)
    {
        _lockFlowController.Unlock(_settings, reason, ResetInactivityCountdown, CloseJabilEyeReconnectPrompt, UpdateLockUi);
    }

    private async void EmergencyUnlock()
    {
        if (!_lockFlowController.IsLocked || _isEmergencyUnlockPromptOpen)
        {
            return;
        }

        _isEmergencyUnlockPromptOpen = true;
        _log.WriteAudit("EMERGENCY HOTKEY PRESSED", $"WindowsUser={Environment.UserName}");
        FaceStateTextBlock.Text = "Emergency unlock requires administrator sign in.";
        CloseJabilEyeReconnectPrompt();
        ActivateMainWindow();

        var dialog = new EmergencyAdminUnlockDialog(_authService)
        {
            XamlRoot = XamlRoot
        };
        dialog.ValidationFailed += EmergencyAdminUnlockDialog_ValidationFailed;

        BeginEmergencyCredentialInputMode();
        try
        {
            var result = await dialog.ShowAsync();
            if (result == ContentDialogResult.Primary && dialog.SignedInAdmin is { IsAdmin: true } admin)
            {
                _log.WriteAudit("EMERGENCY UNLOCK APPROVED", $"Admin={admin.Ntid}; WindowsUser={Environment.UserName}");
                AppSession.SignIn(admin.Ntid, admin.IsAdmin);
                ApplyUserPermissions();
                RefreshAdminList();
                UnlockSystem($"Emergency admin unlock by {admin.Ntid}");
                FaceStateTextBlock.Text = $"Emergency unlock approved by {admin.Ntid}.";
                return;
            }

            _log.WriteAudit("EMERGENCY UNLOCK PROMPT CLOSED", $"WindowsUser={Environment.UserName}");
            _lockFlowController.ApplyCurrentSettings(_settings);
            FaceStateTextBlock.Text = "Emergency unlock cancelled. Waiting for an authorized face match.";
        }
        finally
        {
            dialog.ValidationFailed -= EmergencyAdminUnlockDialog_ValidationFailed;
            _lockFlowController.EndCredentialEntryMode(_settings);
            _isEmergencyUnlockPromptOpen = false;
        }
    }

    private void EmergencyAdminUnlockDialog_ValidationFailed(object? sender, EmergencyAdminUnlockFailedEvent e)
    {
        var ntid = string.IsNullOrWhiteSpace(e.Ntid) ? "(blank)" : e.Ntid;
        _log.WriteAudit("EMERGENCY UNLOCK DENIED", $"Attempt={e.Attempt}; Admin={ntid}; WindowsUser={Environment.UserName}; Error={e.Message}");
    }

    private void BeginEmergencyCredentialInputMode()
    {
        var window = App.ActiveWindow;
        if (window is null)
        {
            _lockFlowController.ApplyCurrentSettings(_settings);
            return;
        }

        var position = window.AppWindow.Position;
        var size = window.AppWindow.Size;
        _lockFlowController.BeginCredentialEntryMode(
            WindowNative.GetWindowHandle(window),
            position.X,
            position.Y,
            position.X + size.Width,
            position.Y + size.Height);
    }

    private void UpdateLockUi()
    {
        UpdateCountdownText();

        if (_lockFlowController.IsLocked)
        {
            StatusCard.Background = new SolidColorBrush(ColorHelper.FromArgb(255, 209, 52, 56));
            StatusCard.BorderBrush = new SolidColorBrush(ColorHelper.FromArgb(255, 164, 38, 44));
            StatusCard.BorderThickness = new Thickness(0);
            LockStateTextBlock.Text = "SYSTEM LOCKED";
            FaceStateTextBlock.Text = "Waiting for an authorized face match.";
            ManualLockButtonText.Text = "Unlock";
            ManualLockIcon.Glyph = "\uE785";
            ManualLockButton.Foreground = new SolidColorBrush(ColorHelper.FromArgb(255, 164, 38, 44));
            StatusIcon.Glyph = "\uE72E";
        }
        else
        {
            StatusCard.Background = new SolidColorBrush(ColorHelper.FromArgb(255, 18, 184, 134));
            StatusCard.BorderThickness = new Thickness(0);
            LockStateTextBlock.Text = "SYSTEM UNLOCKED";
            FaceStateTextBlock.Text = "Active session expires soon";
            ManualLockButtonText.Text = "Manual Lock";
            ManualLockIcon.Glyph = "\uE785";
            ManualLockButton.Foreground = new SolidColorBrush(ColorHelper.FromArgb(255, 33, 132, 93));
            StatusIcon.Glyph = "\uE785";
        }
    }

    private string BuildInputSummary()
    {
        var disabled = new List<string>();
        if (_settings.DisableKeyboardWhenLocked)
        {
            disabled.Add("keyboard");
        }
        if (_settings.DisableMouseWhenLocked)
        {
            disabled.Add("mouse");
        }
        return disabled.Count == 0
            ? "No input devices are disabled for this lock state."
            : $"Disabled while locked: {string.Join(", ", disabled)}.";
    }

    private void RecognitionService_StatusChanged(object? sender, RecognitionStatus status)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            var connectionLabel = JabilEyeConnectionController.GetConnectionLabel(status);
            SettingsCameraStatusTextBlock.Text = $"Status: {connectionLabel}";
            if (!_isConnectingJabilEye)
            {
                SetConnectPiButtonContent(JabilEyeConnectionController.IsEffectivelyConnected(status) ? "Stop Connection" : "Connect");
            }
            RecognitionPage.SetCameraState(_showRecognitionPreview ? connectionLabel : "View Closed");
            RecognitionPage.SetRecognitionStatus(
                _showRecognitionPreview ? BuildRecognitionResultLabel(status) : "",
                _showRecognitionPreview ? status.LastMatchedName ?? "" : "",
                _showRecognitionPreview ? status.LastMatchedEmployeeId ?? "" : "",
                _showRecognitionPreview ? status.LastConfidence : null,
                _showRecognitionPreview ? status.FaceBox : null,
                _showRecognitionPreview ? status.LastLivenessScore : null,
                _showRecognitionPreview ? status.LastLivenessPassed : null,
                _showRecognitionPreview ? status.LastLivenessMessage : null);
            HandleJabilEyeConnectionStatus(status);
            if (_showRecognitionPreview && !JabilEyeConnectionController.IsEffectivelyConnected(status) && !status.IsRunning)
            {
                var message = string.IsNullOrWhiteSpace(status.LastError)
                    ? $"Camera state: {connectionLabel}"
                    : status.LastError;
                RecognitionPage.ClearPreview(message);
            }
        });
    }

    private static string BuildRecognitionResultLabel(RecognitionStatus status)
    {
        if (!status.StreamHealthy)
        {
            return "Offline";
        }

        if (string.Equals(status.LastMatchedName, "Unknown", StringComparison.OrdinalIgnoreCase))
        {
            return "Unknown";
        }

        if (status.LastLivenessPassed == false)
        {
            return "Blink Required";
        }

        return string.IsNullOrWhiteSpace(status.LastMatchedEmployeeId) ? "Scanning" : "Recognized";
    }

    private void HandleJabilEyeConnectionStatus(RecognitionStatus status)
    {
        var connected = JabilEyeConnectionController.IsEffectivelyConnected(status);
        if (_suppressJabilEyeReconnectPrompt && !connected)
        {
            return;
        }

        if (connected)
        {
            _suppressJabilEyeReconnectPrompt = false;
        }

        if (JabilEyeConnectionController.IsDisconnectedForPrompt(status))
        {
            ShowJabilEyeReconnectPrompt(status);
            return;
        }

        if (connected && _jabilEyeReconnectWindow is not null)
        {
            ShowJabilEyeReconnectedThenClose();
        }

        if (!status.IsRunning && _jabilEyeReconnectWindow is not null)
        {
            CloseJabilEyeReconnectPrompt();
        }
    }

    private void ShowJabilEyeReconnectPrompt(RecognitionStatus status)
    {
        _jabilEyeReconnectCloseCts?.Cancel();
        _jabilEyeReconnectCloseCts?.Dispose();
        _jabilEyeReconnectCloseCts = null;

        var hostname = string.IsNullOrWhiteSpace(_settings.JabilEyeHost) ? _settings.CameraHost : _settings.JabilEyeHost;
        if (_jabilEyeReconnectWindow is null)
        {
            _jabilEyeReconnectWindow = new JabilEyeReconnectWindow(hostname, _lockFlowController.IsLocked);
            _jabilEyeReconnectWindow.Closed += (_, _) => _jabilEyeReconnectWindow = null;
            _jabilEyeReconnectWindow.RetryRequested += JabilEyeReconnectWindow_RetryRequested;
            _jabilEyeReconnectWindow.ChangeHostnameRequested += JabilEyeReconnectWindow_ChangeHostnameRequested;
            _jabilEyeReconnectWindow.DismissRequested += JabilEyeReconnectWindow_DismissRequested;
            _jabilEyeReconnectWindow.Activate();
            _log.Write($"JabilEye disconnect prompt opened for {hostname}.");
        }

        _jabilEyeReconnectWindow.ShowDisconnected(hostname, status.LastError, _lockFlowController.IsLocked);
        _jabilEyeReconnectWindow.Activate();
    }

    private void ShowLockWidgetWindow()
    {
        if (_lockWidgetWindow is not null)
        {
            _lockWidgetWindow.Activate();
            return;
        }

        _lockWidgetWindow = new LockWidgetWindow(_recognitionService, _log);
        _lockWidgetWindow.Closed += (_, _) => _lockWidgetWindow = null;
        _lockWidgetWindow.Activate();
    }

    private void SetConnectPiButtonContent(string text)
    {
        ConnectPiButton.Content = text;
        if (string.Equals(text, "Stop Connection", StringComparison.OrdinalIgnoreCase))
        {
            SetConnectPiButtonColors(
                Colors.Firebrick,
                ColorHelper.FromArgb(255, 192, 44, 44),
                ColorHelper.FromArgb(255, 139, 0, 0),
                ColorHelper.FromArgb(255, 245, 204, 204),
                Colors.White,
                Colors.White,
                Colors.White,
                ColorHelper.FromArgb(255, 96, 24, 24),
                ColorHelper.FromArgb(255, 139, 0, 0),
                ColorHelper.FromArgb(255, 96, 24, 24),
                ColorHelper.FromArgb(255, 72, 18, 18),
                ColorHelper.FromArgb(255, 218, 170, 170));
        }
        else
        {
            SetConnectPiButtonColors(
                Colors.White,
                ColorHelper.FromArgb(255, 244, 248, 251),
                ColorHelper.FromArgb(255, 231, 240, 246),
                ColorHelper.FromArgb(255, 238, 243, 246),
                Colors.Black,
                Colors.Black,
                Colors.Black,
                ColorHelper.FromArgb(255, 75, 89, 97),
                ColorHelper.FromArgb(255, 199, 212, 220),
                ColorHelper.FromArgb(255, 154, 170, 180),
                ColorHelper.FromArgb(255, 129, 145, 155),
                ColorHelper.FromArgb(255, 216, 224, 229));
        }
    }

    private void SetConnectPiButtonColors(
        Windows.UI.Color background,
        Windows.UI.Color pointerOverBackground,
        Windows.UI.Color pressedBackground,
        Windows.UI.Color disabledBackground,
        Windows.UI.Color foreground,
        Windows.UI.Color pointerOverForeground,
        Windows.UI.Color pressedForeground,
        Windows.UI.Color disabledForeground,
        Windows.UI.Color border,
        Windows.UI.Color pointerOverBorder,
        Windows.UI.Color pressedBorder,
        Windows.UI.Color disabledBorder)
    {
        ConnectPiButton.Background = new SolidColorBrush(background);
        ConnectPiButton.Foreground = new SolidColorBrush(foreground);
        ConnectPiButton.BorderBrush = new SolidColorBrush(border);
        SetButtonBrushResource("ButtonBackground", background);
        SetButtonBrushResource("ButtonBackgroundPointerOver", pointerOverBackground);
        SetButtonBrushResource("ButtonBackgroundPressed", pressedBackground);
        SetButtonBrushResource("ButtonBackgroundDisabled", disabledBackground);
        SetButtonBrushResource("ButtonForeground", foreground);
        SetButtonBrushResource("ButtonForegroundPointerOver", pointerOverForeground);
        SetButtonBrushResource("ButtonForegroundPressed", pressedForeground);
        SetButtonBrushResource("ButtonForegroundDisabled", disabledForeground);
        SetButtonBrushResource("ButtonBorderBrush", border);
        SetButtonBrushResource("ButtonBorderBrushPointerOver", pointerOverBorder);
        SetButtonBrushResource("ButtonBorderBrushPressed", pressedBorder);
        SetButtonBrushResource("ButtonBorderBrushDisabled", disabledBorder);
    }

    private void SetButtonBrushResource(string key, Windows.UI.Color color)
    {
        ConnectPiButton.Resources[key] = new SolidColorBrush(color);
    }

    private void CloseLockWidgetWindow()
    {
        var window = _lockWidgetWindow;
        _lockWidgetWindow = null;
        window?.Close();
    }

    private async void JabilEyeReconnectWindow_RetryRequested(object? sender, EventArgs e)
    {
        await RetryJabilEyeConnectionAsync();
    }

    private async void JabilEyeReconnectWindow_ChangeHostnameRequested(object? sender, EventArgs e)
    {
        _suppressJabilEyeReconnectPrompt = true;
        CloseJabilEyeReconnectPrompt();
        ActivateMainWindow();

        if (!AppSession.IsAdmin && !await ShowSignInDialogAsync())
        {
            return;
        }

        if (!AppSession.IsAdmin)
        {
            await ShowInfoDialogAsync("Admin required", "Only an admin can change the JabilEye hostname.");
            return;
        }

        if (_lockFlowController.IsLocked)
        {
            _log.WriteAudit("ADMIN EMERGENCY UNLOCK", "Method=Admin hostname change");
            UnlockSystem("Admin hostname change");
        }

        NavigateToHostnameSettings();
    }

    private void JabilEyeReconnectWindow_DismissRequested(object? sender, EventArgs e)
    {
        if (_lockFlowController.IsLocked &&
            sender is not JabilEyeReconnectWindow { IsConnectedState: true })
        {
            return;
        }

        _suppressJabilEyeReconnectPrompt = true;
        CloseJabilEyeReconnectPrompt();
    }

    private async Task RetryJabilEyeConnectionAsync()
    {
        try
        {
            _suppressJabilEyeReconnectPrompt = false;
            ReadSettingsFromForm();
            _settingsService.Save(_settings);
            await _jabilEyeConnectionController.RetryAsync(_settings, _ => _settingsController.PushCameraRotationToPiAsync(_settings));
        }
        catch (Exception ex)
        {
            _log.Write($"JabilEye reconnect retry failed: {ex.Message}");
        }
    }

    private void NavigateToHostnameSettings()
    {
        ActivateMainWindow();
        RootNavigationView.SelectedItem = SettingsNavItem;
        NavigateToPage("Settings", addHistory: true);
        CameraHostTextBox.Focus(FocusState.Programmatic);
        CameraHostTextBox.SelectAll();
    }

    private static void ActivateMainWindow()
    {
        var window = App.ActiveWindow;
        if (window is null)
        {
            return;
        }

        if (window.AppWindow.Presenter is OverlappedPresenter presenter &&
            presenter.State == OverlappedPresenterState.Minimized)
        {
            presenter.Restore();
        }

        window.Activate();
    }

    private void ShowJabilEyeReconnectedThenClose()
    {
        var window = _jabilEyeReconnectWindow;
        if (window is null)
        {
            return;
        }

        _jabilEyeReconnectCloseCts?.Cancel();
        _jabilEyeReconnectCloseCts?.Dispose();
        _jabilEyeReconnectCloseCts = new CancellationTokenSource();
        var token = _jabilEyeReconnectCloseCts.Token;

        window.ShowConnected(_lockFlowController.IsLocked);
        window.Activate();
        _ = CloseJabilEyeReconnectPromptAfterDelayAsync(token);
    }

    private async Task CloseJabilEyeReconnectPromptAfterDelayAsync(CancellationToken cancellationToken)
    {
        try
        {
            await Task.Delay(1800, cancellationToken);
        }
        catch (OperationCanceledException)
        {
            return;
        }

        DispatcherQueue.TryEnqueue(() =>
        {
            _log.Write("JabilEye reconnect prompt auto-closed after reconnect.");
            CloseJabilEyeReconnectPrompt();
        });
    }

    private void CloseJabilEyeReconnectPrompt()
    {
        _jabilEyeReconnectCloseCts?.Cancel();
        _jabilEyeReconnectCloseCts?.Dispose();
        _jabilEyeReconnectCloseCts = null;

        var window = _jabilEyeReconnectWindow;
        if (window is not null)
        {
            window.RetryRequested -= JabilEyeReconnectWindow_RetryRequested;
            window.ChangeHostnameRequested -= JabilEyeReconnectWindow_ChangeHostnameRequested;
            window.DismissRequested -= JabilEyeReconnectWindow_DismissRequested;
        }
        _jabilEyeReconnectWindow = null;
        window?.Close();
    }

    private void RecognitionService_PreviewFrameAvailable(object? sender, PreviewFrame frame)
    {
        if (!_showRecognitionPreview)
        {
            _pendingRecognitionPreviewFrame = null;
            return;
        }

        _pendingRecognitionPreviewFrame = frame;
        if (Interlocked.Exchange(ref _recognitionPreviewRenderActive, 1) != 0)
        {
            return;
        }

        DispatcherQueue.TryEnqueue(async () => await DrainRecognitionPreviewFramesAsync());
    }

    private async Task DrainRecognitionPreviewFramesAsync()
    {
        var generation = _recognitionPreviewGeneration;
        try
        {
            while (_pendingRecognitionPreviewFrame is { } frame)
            {
                _pendingRecognitionPreviewFrame = null;
                if (!_showRecognitionPreview || generation != _recognitionPreviewGeneration)
                {
                    continue;
                }

                var wait = RecognitionPreviewMinInterval - (DateTimeOffset.Now - _lastRecognitionPreviewRenderAt);
                if (wait > TimeSpan.Zero)
                {
                    await Task.Delay(wait);
                }

                if (!_showRecognitionPreview || generation != _recognitionPreviewGeneration)
                {
                    continue;
                }

                await RenderRecognitionPreviewFrameAsync(frame, generation);
            }
        }
        finally
        {
            Interlocked.Exchange(ref _recognitionPreviewRenderActive, 0);
            if (_pendingRecognitionPreviewFrame is not null &&
                Interlocked.Exchange(ref _recognitionPreviewRenderActive, 1) == 0)
            {
                DispatcherQueue.TryEnqueue(async () => await DrainRecognitionPreviewFramesAsync());
            }
        }
    }

    private async Task RenderRecognitionPreviewFrameAsync(PreviewFrame frame, int generation)
    {
        if (!_showRecognitionPreview || generation != _recognitionPreviewGeneration)
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
            if (!_showRecognitionPreview || generation != _recognitionPreviewGeneration)
            {
                return;
            }
            RecognitionPage.SetPreviewImage(bitmap);
            _lastRecognitionPreviewRenderAt = DateTimeOffset.Now;
        }
        catch (Exception ex)
        {
            RecognitionPage.ShowPreviewMessage($"Preview failed: {ex.Message}");
            _log.Write($"Preview failed: {ex.Message}");
        }
    }

    private void RecognitionService_UnlockRecognized(object? sender, RecognitionUnlockEvent e)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            if (_lockFlowController.IsLocked)
            {
                UnlockSystem($"Face match {e.EmployeeId} ({e.Confidence:0.0}%)");
            }
            else
            {
                ResetInactivityCountdown();
                _log.Write($"Authorized face detected: {e.Name} / {e.EmployeeId} ({e.Confidence:0.0}%).");
            }
        });
    }

    private async void SaveSettingsButton_Click(object sender, RoutedEventArgs e)
    {
        ReadSettingsFromForm();
        ResetInactivityCountdown();
        await _settingsController.SaveSettingsAsync(_settings);
        UpdateLockUi();
        RefreshUsers();
    }

    private async void SettingsControl_SaveOnLostFocus(object sender, RoutedEventArgs e)
    {
        await AutoSaveSettingsAsync(pushPiSettings: false);
    }

    private async void SettingsControl_SaveOnToggle(object sender, RoutedEventArgs e)
    {
        await AutoSaveSettingsAsync(pushPiSettings: false);
    }

    private async void SettingsControl_SaveOnSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        await AutoSaveSettingsAsync(pushPiSettings: true);
    }

    private async void LockTimeoutControl_LostFocus(object sender, RoutedEventArgs e)
    {
        await AutoSaveSettingsAsync(pushPiSettings: false);
    }

    private async Task AutoSaveSettingsAsync(bool pushPiSettings)
    {
        if (_isLoadingSettings || _isAutoSavingSettings)
        {
            return;
        }

        _isAutoSavingSettings = true;
        try
        {
            ReadSettingsFromForm();
            _settingsService.Save(_settings);
            _lockFlowController.ApplyCurrentSettings(_settings);
            ResetInactivityCountdown();

            if (pushPiSettings)
            {
                await _settingsController.PushCameraRotationToPiAsync(_settings);
            }

            UpdateLockUi();
        }
        catch (Exception ex)
        {
            _log.Write($"Settings auto-save warning: {ex.Message}");
        }
        finally
        {
            _isAutoSavingSettings = false;
        }
    }

    private async void StartRecognitionButton_Click(object sender, RoutedEventArgs e)
    {
        if (_isConnectingJabilEye)
        {
            return;
        }

        if (JabilEyeConnectionController.IsEffectivelyConnected(_recognitionService.CurrentStatus))
        {
            _isConnectingJabilEye = true;
            ConnectPiButton.IsEnabled = false;
            ConnectPiProgressRing.IsActive = true;
            ConnectPiProgressRing.Visibility = Visibility.Visible;
            SettingsCameraStatusTextBlock.Text = "Status: Stopping connection...";
            try
            {
                await _recognitionService.StopAsync();
                _showRecognitionPreview = false;
                _recognitionPreviewGeneration++;
                _pendingRecognitionPreviewFrame = null;
                RecognitionPage.ClearPreview("Camera disconnected. Press Open Camera or Connect to start again.");
                RecognitionPage.SetCameraState("Disconnected");
                SettingsCameraStatusTextBlock.Text = "Status: Disconnected";
                SetConnectPiButtonContent("Connect");
                _suppressJabilEyeReconnectPrompt = true;
                CloseJabilEyeReconnectPrompt();
                _log.WriteAudit("JABILEYE DISCONNECTED", $"Host={_settings.JabilEyeHost}");
            }
            finally
            {
                ConnectPiProgressRing.IsActive = false;
                ConnectPiProgressRing.Visibility = Visibility.Collapsed;
                ConnectPiButton.IsEnabled = true;
                _isConnectingJabilEye = false;
            }
            return;
        }

        _isConnectingJabilEye = true;
        _suppressJabilEyeReconnectPrompt = false;
        _showRecognitionPreview = true;
        _recognitionPreviewGeneration++;
        if (!RecognitionPage.HasPreviewImage)
        {
            RecognitionPage.ClearPreview("Connecting to camera...");
        }
        ConnectPiButton.IsEnabled = false;
        SetConnectPiButtonContent("Connecting...");
        ConnectPiProgressRing.IsActive = true;
        ConnectPiProgressRing.Visibility = Visibility.Visible;
        SettingsCameraStatusTextBlock.Text = "Status: Connecting...";
        ReadSettingsFromForm();
        _settingsService.Save(_settings);
        try
        {
            var result = await _jabilEyeConnectionController.ConnectAsync(
                _settings,
                _ => _settingsController.PushCameraRotationToPiAsync(_settings),
                RefreshUsers,
                TimeSpan.FromSeconds(6));
            if (result.Connected)
            {
                SettingsCameraStatusTextBlock.Text = "Status: Connected";
                SetConnectPiButtonContent("Stop Connection");
                await ShowInfoDialogAsync("Camera connected", $"Connected to {_settings.JabilEyeHost}.");
            }
            else
            {
                SettingsCameraStatusTextBlock.Text = "Status: Disconnected";
                SetConnectPiButtonContent("Connect");
                HandleJabilEyeConnectionStatus(result.Status);
                var title = JabilEyeConnectionController.IsAlreadyConnectedByAnotherSas(result.Message)
                    ? "Camera already in use"
                    : "Camera connection failed";
                await ShowInfoDialogAsync(title, result.Message);
            }
        }
        catch (Exception ex)
        {
            SettingsCameraStatusTextBlock.Text = "Status: Disconnected";
            SetConnectPiButtonContent("Connect");
            HandleJabilEyeConnectionStatus(_recognitionService.CurrentStatus);
            await ShowInfoDialogAsync("Camera connection failed", ex.Message);
        }
        finally
        {
            ConnectPiProgressRing.IsActive = false;
            ConnectPiProgressRing.Visibility = Visibility.Collapsed;
            ConnectPiButton.IsEnabled = true;
            SetConnectPiButtonContent(JabilEyeConnectionController.IsEffectivelyConnected(_recognitionService.CurrentStatus) ? "Stop Connection" : "Connect");
            _isConnectingJabilEye = false;
        }
    }

    private void StopRecognitionButton_Click(object sender, RoutedEventArgs e)
    {
        _showRecognitionPreview = false;
        _recognitionPreviewGeneration++;
        _pendingRecognitionPreviewFrame = null;
        RecognitionPage.ClearPreview("Camera view is closed. Recognition is still running.");
        RecognitionPage.SetCameraState("View Closed");
        _log.Write("Recognition camera view closed by user; recognition remains running.");
    }

    private async void OpenCameraButton_Click(object sender, RoutedEventArgs e)
    {
        _suppressJabilEyeReconnectPrompt = false;
        _showRecognitionPreview = true;
        _recognitionPreviewGeneration++;
        ReadSettingsFromForm();
        _settings.CameraSource = "rtsp";
        _settingsService.Save(_settings);
        if (!RecognitionPage.HasPreviewImage)
        {
            RecognitionPage.ShowPreviewMessage("Opening camera view...");
        }
        await _recognitionService.ConfigureAsync(_settings);
        if (!_recognitionService.CurrentStatus.IsRunning)
        {
            await _recognitionService.StartAsync();
        }
        RefreshUsers();
    }

    private void CloseCameraButton_Click(object sender, RoutedEventArgs e)
    {
        _showRecognitionPreview = false;
        _recognitionPreviewGeneration++;
        _pendingRecognitionPreviewFrame = null;
        RecognitionPage.ClearPreview("Camera view is closed. Press Open Camera to view again.");
        RecognitionPage.SetCameraState("View Closed");
        _log.Write("Face Recognition camera view closed by user; recognition remains running.");
    }

    private async void RegisterFaceButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var user = await _recognitionService.RegisterCurrentFaceAsync(RecognitionPage.RegisterName, RecognitionPage.RegisterEmployeeId);
            RecognitionPage.RegisterName = "";
            RecognitionPage.RegisterEmployeeId = "";
            RefreshUsers();
            _log.Write($"Capture complete: {user.DisplayName} / {user.EmployeeId}, samples={user.SampleCount}.");
            _log.WriteAudit("FACE USER REGISTERED", $"EmployeeId={user.EmployeeId}; Name={user.DisplayName}; Samples={user.SampleCount}");
            await ShowInfoDialogAsync("Capture complete", $"{user.DisplayName} now has {user.SampleCount} face sample{(user.SampleCount == 1 ? "" : "s")}.");
        }
        catch (Exception ex)
        {
            _log.Write($"Capture failed: {ex.Message}");
            await ShowInfoDialogAsync("Capture failed", ex.Message);
        }
    }

    private async void DeleteFaceButton_Click(object sender, RoutedEventArgs e)
    {
        var employeeId = RecognitionPage.RegisterEmployeeId.Trim();
        var displayName = RecognitionPage.RegisterName.Trim();
        if (string.IsNullOrWhiteSpace(employeeId))
        {
            _log.Write("Delete failed: Employee ID / NTID is required.");
            return;
        }

        if (!await ConfirmAsync("Delete authorized user?", $"Delete {displayName} / {employeeId}? This removes all saved face samples."))
        {
            return;
        }

        var deleted = await _recognitionService.DeleteUserAsync(employeeId);
        RefreshUsers();
        _log.Write(deleted ? $"Delete complete: {employeeId}." : $"Delete skipped: {employeeId} not found.");
        _log.WriteAudit(deleted ? "FACE USER DELETED" : "FACE USER DELETE SKIPPED", $"EmployeeId={employeeId}; Name={displayName}");
    }

    private static IntPtr GetPickerOwnerWindow()
    {
        return App.ActiveWindow is null
            ? throw new InvalidOperationException("The app window is not available for the picker.")
            : WindowNative.GetWindowHandle(App.ActiveWindow);
    }

    private async void SelectExportFolderButton_Click(object sender, RoutedEventArgs e)
    {
        var previousPath = ExportFolderTextBox.Text;
        ExportFolderTextBox.Text = "";
        FaceDataInfoBar.IsOpen = false;
        try
        {
            var picker = new FolderPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary
            };
            picker.FileTypeFilter.Add("*");
            InitializeWithWindow.Initialize(picker, GetPickerOwnerWindow());

            var folder = await picker.PickSingleFolderAsync();
            ExportFolderTextBox.Text = folder?.Path ?? previousPath;
        }
        catch (Exception ex)
        {
            _log.Write($"Export folder picker failed: {ex}");
        }
    }

    private async void SelectImportZipButton_Click(object sender, RoutedEventArgs e)
    {
        var previousPath = ImportZipTextBox.Text;
        ImportZipTextBox.Text = "";
        FaceDataInfoBar.IsOpen = false;
        try
        {
            var picker = new FileOpenPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary
            };
            picker.FileTypeFilter.Add(".zip");
            InitializeWithWindow.Initialize(picker, GetPickerOwnerWindow());

            var file = await picker.PickSingleFileAsync();
            ImportZipTextBox.Text = file?.Path ?? previousPath;
        }
        catch (Exception ex)
        {
            _log.Write($"Import ZIP picker failed: {ex}");
        }
    }

    private async void SelectServerMountPathButton_Click(object sender, RoutedEventArgs e)
    {
        var previousPath = RtspPathTextBox.Text;
        RtspPathTextBox.Text = "";
        try
        {
            var picker = new FolderPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary
            };
            picker.FileTypeFilter.Add("*");
            InitializeWithWindow.Initialize(picker, GetPickerOwnerWindow());

            var folder = await picker.PickSingleFolderAsync();
            RtspPathTextBox.Text = folder?.Path ?? previousPath;
        }
        catch (Exception ex)
        {
            RtspPathTextBox.Text = previousPath;
            _log.Write($"Server mount path picker failed: {ex}");
        }
    }

    private async void ExportFaceDataButton_Click(object sender, RoutedEventArgs e)
    {
        if (_faceDataController is null)
        {
            return;
        }

        await SyncPiApiToSettingsFormAsync(save: true);
        var exportPath = ExportFolderTextBox.Text.Trim();
        var exportLocal = ExportModeComboBox.SelectedIndex == 0;
        AppSettings? serverCredentials = null;
        if (!exportLocal)
        {
            serverCredentials = FaceDataController.CreateTemporaryServerSettings(
                _settings,
                ExportSmbUsernameTextBox.Text,
                ExportSmbPasswordBox.Password,
                exportPath);
            if (serverCredentials is null)
            {
                await ShowInfoDialogAsync("Credentials required", "Enter the NTID, Password, and export path for this export.");
                return;
            }

            exportPath = serverCredentials.ServerPath;
        }

        SetFaceDataOperationState(true, exportLocal ? "Exporting face data to local folder..." : "Exporting face data to SMB/server path...");
        try
        {
            var zipPath = await _faceDataController.ExportAsync(new FaceDataExportRequest(exportLocal, exportPath, serverCredentials));
            ShowFaceDataMessage("Export complete", $"Face data backup created: {zipPath}", InfoBarSeverity.Success);
        }
        catch (Exception ex)
        {
            _log.Write($"Export failed: {ex}");
            ShowFaceDataMessage("Export failed", ex.Message, InfoBarSeverity.Error);
        }
        finally
        {
            if (!exportLocal)
            {
                ClearExportSmbFields();
            }

            SetFaceDataOperationState(false);
        }
    }

    private async void ImportFaceDataButton_Click(object sender, RoutedEventArgs e)
    {
        if (_faceDataController is null)
        {
            return;
        }

        await SyncPiApiToSettingsFormAsync(save: true);
        var importZipPath = ImportZipTextBox.Text.Trim();
        var importLocal = ImportModeComboBox.SelectedIndex == 0;
        if (!importLocal)
        {
            importZipPath = FaceDataController.NormalizeServerPath(importZipPath);
        }

        AppSettings? serverCredentials = null;
        if (!importLocal)
        {
            serverCredentials = FaceDataController.CreateTemporaryServerSettings(
                _settings,
                ImportSmbUsernameTextBox.Text,
                ImportSmbPasswordBox.Password,
                FaceDataController.GetServerMountPathFromImportPath(importZipPath));
            if (serverCredentials is null)
            {
                await ShowInfoDialogAsync("Credentials required", "Enter the NTID, Password, and ZIP path for this import.");
                return;
            }
        }

        SetFaceDataOperationState(true, importLocal ? "Importing local ZIP into JabilEye data..." : "Importing server ZIP into JabilEye data...");
        try
        {
            var added = await _faceDataController.ImportAsync(new FaceDataImportRequest(importLocal, importZipPath, serverCredentials));
            RefreshUsers();
            ShowFaceDataMessage("Import complete", $"Face data imported. {added} new user{(added == 1 ? "" : "s")} added.", InfoBarSeverity.Success);
        }
        catch (FaceDataValidationException ex)
        {
            await ShowInfoDialogAsync(ex.Title, ex.Message);
        }
        catch (Exception ex)
        {
            _log.Write($"Import failed: {ex}");
            ShowFaceDataMessage("Import failed", FaceDataController.BuildImportErrorMessage(ex), InfoBarSeverity.Error);
        }
        finally
        {
            if (!importLocal)
            {
                ClearImportSmbFields();
            }

            SetFaceDataOperationState(false);
        }
    }




    private void SetFaceDataOperationState(bool isRunning, string message = "")
    {
        FaceDataProgressBar.Visibility = isRunning ? Visibility.Visible : Visibility.Collapsed;
        ExportFaceDataButton.IsEnabled = !isRunning;
        ImportFaceDataButton.IsEnabled = !isRunning;
        ExportModeComboBox.IsEnabled = !isRunning;
        ImportModeComboBox.IsEnabled = !isRunning;
        SelectExportFolderButton.IsEnabled = !isRunning;
        SelectImportZipButton.IsEnabled = !isRunning;
        ExportFolderTextBox.IsEnabled = !isRunning;
        ImportZipTextBox.IsEnabled = !isRunning;
        ExportSmbUsernameTextBox.IsEnabled = !isRunning;
        ExportSmbPasswordBox.IsEnabled = !isRunning;
        ImportSmbUsernameTextBox.IsEnabled = !isRunning;
        ImportSmbPasswordBox.IsEnabled = !isRunning;

        if (isRunning)
        {
            FaceDataInfoBar.Title = "Please wait";
            FaceDataInfoBar.Message = message;
            FaceDataInfoBar.Severity = InfoBarSeverity.Informational;
            FaceDataInfoBar.IsOpen = true;
        }
    }
    private void ShowFaceDataMessage(string title, string message, InfoBarSeverity severity)
    {
        FaceDataInfoBar.Title = title;
        FaceDataInfoBar.Message = message;
        FaceDataInfoBar.Severity = severity;
        FaceDataInfoBar.IsOpen = true;
    }

    private void ShowLogsMessage(string title, string message, InfoBarSeverity severity)
    {
        LogsPage.ShowMessage(title, message, severity);
    }

    private void SetLogsOperationState(bool busy, string message = "")
    {
        LogsPage.SetOperationState(busy, message);
    }

    private async Task SyncPiApiToSettingsFormAsync(bool save)
    {
        ReadSettingsFromForm();
        if (save)
        {
            _settingsService.Save(_settings);
        }

        await _recognitionService.ConfigureAsync(_settings);
    }

    private async Task<string?> JabilEyeckLogDestinationFolderAsync()
    {
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary
        };
        picker.FileTypeFilter.Add("*");
        InitializeWithWindow.Initialize(picker, GetPickerOwnerWindow());

        var folder = await picker.PickSingleFolderAsync();
        return folder?.Path;
    }

    private async void BrowseSasLogFolderButton_Click(object sender, RoutedEventArgs e)
    {
        var folder = await JabilEyeckLogDestinationFolderAsync();
        if (!string.IsNullOrWhiteSpace(folder))
        {
            LogsPage.SasDestinationFolder = folder;
        }
    }

    private async void DownloadSasLogButton_Click(object sender, RoutedEventArgs e)
    {
        SetLogsOperationState(true, "Preparing SAS log download...");
        try
        {
            var path = await _logsController.DownloadSasLogAsync(LogsPage.SasDestinationFolder);
            LogsPage.SasLogPath = _log.TodayLogPath;
            ShowLogsMessage("SAS log downloaded", $"Saved to {path}", InfoBarSeverity.Success);
        }
        catch (Exception ex)
        {
            _log.Write($"SAS log download failed: {ex.Message}");
            ShowLogsMessage("SAS log download failed", ex.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SetLogsOperationState(false);
        }
    }


    private void ExportModeComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ExportFolderTextBox is null || ExportSmbCredentialPanel is null)
        {
            return;
        }

        var server = ExportModeComboBox.SelectedIndex == 1;
        ExportFolderTextBox.Header = server ? "SMB/server export path" : "Local export folder";
        ExportFolderTextBox.PlaceholderText = server ? "//server/share/export-folder" : "Choose a folder on this PC";
        SelectExportFolderButton.IsEnabled = true;
        ExportSmbCredentialPanel.Visibility = server ? Visibility.Visible : Visibility.Collapsed;
        if (server && string.IsNullOrWhiteSpace(ExportFolderTextBox.Text))
        {
            ExportFolderTextBox.Text = _settings.ServerPath;
        }
    }

    private void ImportModeComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ImportZipTextBox is null || ImportSmbCredentialPanel is null)
        {
            return;
        }

        var server = ImportModeComboBox.SelectedIndex == 1;
        ImportZipTextBox.Header = server ? "SMB/server ZIP path" : "Local ZIP path";
        ImportZipTextBox.PlaceholderText = server ? "/mnt/server/face_data_20260727.zip" : "Choose a SAS face dataset ZIP";
        SelectImportZipButton.IsEnabled = true;
        ImportSmbCredentialPanel.Visibility = server ? Visibility.Visible : Visibility.Collapsed;
    }

    private async Task ShowInfoDialogAsync(string title, string message)
    {
        await _dialogSemaphore.WaitAsync();
        try
        {
            var dialog = new ContentDialog
            {
                Title = title,
                Content = message,
                CloseButtonText = "OK",
                XamlRoot = XamlRoot
            };

            await dialog.ShowAsync();
        }
        catch (Exception ex)
        {
            _log.Write($"Dialog failed: {title}: {ex.Message}");
        }
        finally
        {
            _dialogSemaphore.Release();
        }
    }

    private void ClearExportSmbFields()
    {
        ExportSmbUsernameTextBox.Text = "";
        ExportSmbPasswordBox.Password = "";
        if (ExportModeComboBox.SelectedIndex == 1)
        {
            ExportFolderTextBox.Text = "";
        }
    }

    private void ClearImportSmbFields()
    {
        ImportSmbUsernameTextBox.Text = "";
        ImportSmbPasswordBox.Password = "";
        if (ImportModeComboBox.SelectedIndex == 1)
        {
            ImportZipTextBox.Text = "";
        }
    }


    private async Task<bool> ConfirmActionAsync(string title, string message, string primaryButtonText)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            PrimaryButtonText = primaryButtonText,
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            XamlRoot = XamlRoot
        };

        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }
    private async Task<bool> ConfirmAsync(string title, string message)
    {
        var dialog = new ContentDialog
        {
            Title = title,
            Content = message,
            PrimaryButtonText = "Delete",
            CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close,
            XamlRoot = XamlRoot
        };

        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private void UserSearchTextBox_TextChanged(object sender, TextChangedEventArgs e)
    {
        RefreshUsers();
    }

    private void CameraSourceComboBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        UpdateCameraSourceUi();
    }

    private void LoadLockTimeoutToForm(int totalSeconds)
    {
        totalSeconds = Math.Max(1, totalSeconds);

        if (totalSeconds % 3600 == 0)
        {
            LockTimeoutValueBox.Value = Math.Clamp(totalSeconds / 3600, 1, 999);
            LockTimeoutUnitComboBox.SelectedIndex = 2;
            return;
        }

        if (totalSeconds % 60 == 0)
        {
            LockTimeoutValueBox.Value = Math.Clamp(totalSeconds / 60, 1, 999);
            LockTimeoutUnitComboBox.SelectedIndex = 1;
            return;
        }

        LockTimeoutValueBox.Value = Math.Clamp(totalSeconds, 1, 999);
        LockTimeoutUnitComboBox.SelectedIndex = 0;
    }

    private int ReadLockTimeoutSecondsFromForm()
    {
        var value = ReadNumberBoxInt(LockTimeoutValueBox, 1, 999);
        return LockTimeoutUnitComboBox.SelectedIndex switch
        {
            2 => value * 3600,
            1 => value * 60,
            _ => value
        };
    }

    private static int ReadNumberBoxInt(NumberBox numberBox, int minimum, int maximum)
    {
        if (double.IsNaN(numberBox.Value))
        {
            return minimum;
        }

        return Math.Clamp((int)Math.Round(numberBox.Value), minimum, maximum);
    }

    private void UpdateCameraSourceUi()
    {
        if (CameraHostTextBox is null)
        {
            return;
        }

        CameraHostTextBox.IsEnabled = true;
        CameraRtspUserTextBox.IsEnabled = true;
        CameraRtspPasswordBox.IsEnabled = true;
        RtspPortTextBox.IsEnabled = true;
        RtspUserTextBox.IsEnabled = true;
        RtspPasswordBox.IsEnabled = true;
        RtspPathTextBox.IsEnabled = true;
        SelectServerMountPathButton.IsEnabled = true;
        SettingsCameraStatusTextBlock.Text = string.IsNullOrWhiteSpace(CameraHostTextBox.Text)
            ? "Status: Disconnected"
            : $"Status: {JabilEyeConnectionController.GetConnectionLabel(_recognitionService.CurrentStatus)}";
    }

    private async void MountServerButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            ReadSettingsFromForm();
            _settingsService.Save(_settings);
            var hasMountDetails = !string.IsNullOrWhiteSpace(_settings.ServerPath) &&
                !string.IsNullOrWhiteSpace(_settings.ServerUsername) &&
                !string.IsNullOrWhiteSpace(_settings.ServerPassword);
            if (hasMountDetails)
            {
                await _recognitionService.ConfigureAsync(_settings);
                await _settingsController.MountServerAsync(_settings);
            }

            await ShowInfoDialogAsync(
                hasMountDetails ? "Server saved" : "Settings saved",
                hasMountDetails
                    ? "The server path was saved for SAS log writing. Logs will be written under SAS_LOG."
                    : "Server mount details are blank, so only the local settings were saved.");
        }
        catch (Exception ex)
        {
            _log.Write($"Server mount failed: {ex.Message}");
            await ShowInfoDialogAsync("Server mount failed", ex.Message);
        }
    }

    private async void ViewDashboardUsersButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshUsers();
        var rows = new ObservableCollection<FaceUserListItem>();
        var dialogListHeight = Math.Clamp(ActualHeight - 280, 220, 520);
        var searchBox = new TextBox
        {
            PlaceholderText = "Search employee ID or name",
            Margin = new Thickness(0, 0, 0, 12)
        };
        var usersList = new ListView
        {
            ItemsSource = rows,
            SelectionMode = ListViewSelectionMode.None,
            Height = dialogListHeight,
            VerticalAlignment = VerticalAlignment.Stretch,
            ItemTemplate = CreateUserItemTemplate()
        };

        void Populate(string keyword)
        {
            rows.Clear();
            var users = _recognitionService.Users
                .Where(user =>
                    string.IsNullOrWhiteSpace(keyword)
                    || user.EmployeeId.Contains(keyword, StringComparison.OrdinalIgnoreCase)
                    || user.DisplayName.Contains(keyword, StringComparison.OrdinalIgnoreCase))
                .OrderBy(user => user.EmployeeId)
                .ToList();

            foreach (var user in users)
            {
                rows.Add(new FaceUserListItem(user.EmployeeId, user.DisplayName, user.SampleCount));
            }

            if (rows.Count == 0)
            {
                rows.Add(new FaceUserListItem("", "No users found", 0));
            }
        }

        searchBox.TextChanged += (_, _) => Populate(searchBox.Text.Trim());
        Populate("");

        var content = new Grid
        {
            MaxHeight = Math.Max(320, ActualHeight - 180)
        };
        content.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        content.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        content.Children.Add(searchBox);
        Grid.SetRow(usersList, 1);
        content.Children.Add(usersList);

        var dialog = new ContentDialog
        {
            Title = "Authorized Users",
            Content = content,
            CloseButtonText = "Close",
            XamlRoot = XamlRoot
        };

        await dialog.ShowAsync();
    }

    private static DataTemplate CreateUserItemTemplate()
    {
        return (DataTemplate)XamlReader.Load(
            """
            <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
                <Grid Padding="0,8" ColumnSpacing="12">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="96" />
                        <ColumnDefinition Width="*" />
                    </Grid.ColumnDefinitions>
                    <TextBlock Text="{Binding EmployeeId}" FontSize="14" FontWeight="SemiBold" TextTrimming="CharacterEllipsis" />
                    <TextBlock Grid.Column="1" Text="{Binding DisplayName}" FontSize="14" TextTrimming="CharacterEllipsis" />
                </Grid>
            </DataTemplate>
            """);
    }


    private void ManualLockButton_Click(object sender, RoutedEventArgs e)
    {
        if (_lockFlowController.IsLocked)
        {
            UnlockSystem("Manual");
        }
        else
        {
            LockSystem("Manual");
        }
    }

    private void RefreshUsers()
    {
        var keyword = RecognitionPage?.UserSearchText ?? "";
        var users = _recognitionService.Users
            .Where(user =>
                string.IsNullOrWhiteSpace(keyword)
                || user.EmployeeId.Contains(keyword, StringComparison.OrdinalIgnoreCase)
                || user.DisplayName.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            .OrderBy(user => user.EmployeeId)
            .ToList();

        _userRows.Clear();
        foreach (var user in users)
        {
            _userRows.Add(new FaceUserListItem(user.EmployeeId, user.DisplayName, user.SampleCount));
        }

        var total = _recognitionService.Users.Count;
        DashboardUsersCountTextBlock.Text = total > 99 ? "99+" : total.ToString();
        if (RecognitionPage is not null)
        {
            RecognitionPage.SetUsersSubtitle(string.IsNullOrWhiteSpace(keyword)
                ? $"{total} active records"
                : $"{users.Count} / {total} matched");
        }
    }

    private async void RootNavigationView_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItem is not NavigationViewItem item || item.Tag is null)
        {
            return;
        }

        var tag = item.Tag.ToString()!;
        if (tag == "Account")
        {
            ShowAccountFlyout();
            RootNavigationView.SelectedItem = GetNavItem(_currentPageTag) ?? DashboardNavItem;
            return;
        }

        if (tag == "SignIn")
        {
            await ShowSignInDialogAsync();
            RootNavigationView.SelectedItem = GetNavItem(_currentPageTag) ?? DashboardNavItem;
            return;
        }
if (!CanAccessPage(tag))
        {
            ResetNavigationToDashboard();
            return;
        }

        NavigateToPage(tag, addHistory: !_isNavigatingBack);
    }
    private void ShowAccountFlyout()
    {
        AccountNavItem.ContextFlyout?.ShowAt(AccountNavItem);
    }

    private async void LogOutFlyoutItem_Click(object sender, RoutedEventArgs e)
    {
        await SignOutAsync();
    }

    private async void SwitchAccountFlyoutItem_Click(object sender, RoutedEventArgs e)
    {
        await ShowSignInDialogAsync();
    }
    private async Task<bool> ShowSignInDialogAsync()
    {
        var dialog = new SignInDialog(_authService)
        {
            XamlRoot = XamlRoot
        };

        if (await dialog.ShowAsync() != ContentDialogResult.Primary || dialog.SignedInUser is null)
        {
            return false;
        }

        var user = dialog.SignedInUser;
        AppSession.SignIn(user.Ntid, user.IsAdmin);
        _pageBackStack.Clear();
        UpdateBackAvailability();
        ApplyUserPermissions();
        LoadSettingsToForm();
        RefreshAdminList();
        _log.Write($"User signed in: {user.Ntid}{(user.IsAdmin ? " admin" : "")}." );
        if (!user.IsAdmin)
        {
            NavigateToPage("Dashboard", addHistory: false);
            RootNavigationView.SelectedItem = DashboardNavItem;
        }

        return true;
    }
    private async Task SignOutAsync()
    {
        AppSession.SignOut();
        _log.Write("User signed out.");
        ApplyUserPermissions();
        LoadSettingsToForm();
        _suppressJabilEyeReconnectPrompt = false;
        HandleJabilEyeConnectionStatus(_recognitionService.CurrentStatus);
        _lockFlowController.ApplyCurrentSettings(_settings);
        ResetNavigationToDashboard();
        await Task.CompletedTask;
    }

    private static bool IsAdminPage(string tag)
    {
        return tag is "Recognition" or "FaceData" or "Logs" or "Settings";
    }

    private static bool CanAccessPage(string tag)
    {
        return tag == "Dashboard" || AppSession.IsAdmin || !IsAdminPage(tag);
    }

    private void ResetNavigationToDashboard()
    {
        _pageBackStack.Clear();
        UpdateBackAvailability();
        NavigateToPage("Dashboard", addHistory: false);
        RootNavigationView.SelectedItem = DashboardNavItem;
    }

    public void ToggleNavigationPane()
    {
        RootNavigationView.IsPaneOpen = !RootNavigationView.IsPaneOpen;
        UpdatePaneHeader();
    }

    public void NavigateBackFromTitleBar()
    {
        NavigateBack();
    }
    private void RootNavigationView_BackRequested(NavigationView sender, NavigationViewBackRequestedEventArgs args)
    {
        NavigateBack();
    }

    private void NavigateBack()
    {
        while (_pageBackStack.Count > 0)
        {
            var previousTag = _pageBackStack.Pop();
            if (!CanAccessPage(previousTag))
            {
                continue;
            }

            _isNavigatingBack = true;
            RootNavigationView.SelectedItem = GetNavItem(previousTag);
            NavigateToPage(previousTag, addHistory: false);
            _isNavigatingBack = false;
            UpdateBackAvailability();
            return;
        }

        ResetNavigationToDashboard();
    }

    private void NavigateToPage(string tag, bool addHistory)
    {
        if (!CanAccessPage(tag))
        {
            tag = "Dashboard";
            addHistory = false;
        }

        if (tag == _currentPageTag)
        {
            UpdateBackAvailability();
            return;
        }

        if (addHistory && !string.IsNullOrWhiteSpace(_currentPageTag))
        {
            _pageBackStack.Push(_currentPageTag);
        }

        _currentPageTag = tag;
        UpdateBackAvailability();

        switch (tag)
        {
            case "Dashboard":
                ShowPage(DashboardPage);
                break;
            case "Recognition":
                ShowPage(RecognitionPage);
                break;
            case "FaceData":
                ShowPage(FaceDataPage);
                break;
            case "Logs":
                LogsPage.SasLogPath = _log.TodayLogPath;
                ShowPage(LogsPage);
                break;
            case "Settings":
                ShowPage(SettingsPage);
                break;
        }

        _log.WriteAudit("PAGE OPENED", tag);
    }


    private void UpdateBackAvailability()
    {
        var canGoBack = _pageBackStack.Count > 0;
        RootNavigationView.IsBackEnabled = canGoBack;
        BackAvailabilityChanged?.Invoke(this, canGoBack);
    }
    private NavigationViewItem? GetNavItem(string tag)
    {
        return tag switch
        {
            "Dashboard" => DashboardNavItem,
            "Recognition" => RecognitionNavItem,
            "FaceData" => FaceDataNavItem,
            "Logs" => LogsNavItem,
            "Settings" => SettingsNavItem,
            _ => null
        };
    }
    private void RootNavigationView_PaneStateChanged(NavigationView sender, object args)
    {
        UpdatePaneHeader();
    }
    private void UpdatePaneHeader()
    {
        if (PaneHeaderText is null)
        {
            return;
        }

        PaneHeaderGrid.Visibility = RootNavigationView.IsPaneOpen ? Visibility.Visible : Visibility.Collapsed;
        PaneHeaderText.Visibility = RootNavigationView.IsPaneOpen ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ShowPage(UIElement page)
    {
        if (ReferenceEquals(_currentPage, page))
        {
            return;
        }

        DashboardPage.Visibility = Visibility.Collapsed;
        RecognitionPage.Visibility = Visibility.Collapsed;
        FaceDataPage.Visibility = Visibility.Collapsed;
        LogsPage.Visibility = Visibility.Collapsed;
        SettingsPage.Visibility = Visibility.Collapsed;

        page.Opacity = 0;
        page.RenderTransform = new TranslateTransform { X = 28 };
        page.Visibility = Visibility.Visible;
        _currentPage = page;
        AnimatePageEntrance(page);
    }

    private static void AnimatePageEntrance(UIElement page)
    {
        var storyboard = new Storyboard();
        var duration = new Duration(TimeSpan.FromMilliseconds(240));
        var easing = new CubicEase { EasingMode = EasingMode.EaseOut };

        var opacity = new DoubleAnimation
        {
            From = 0,
            To = 1,
            Duration = duration,
            EasingFunction = easing
        };
        Storyboard.SetTarget(opacity, page);
        Storyboard.SetTargetProperty(opacity, "Opacity");

        var translate = new DoubleAnimation
        {
            From = 28,
            To = 0,
            Duration = duration,
            EasingFunction = easing
        };
        Storyboard.SetTarget(translate, page);
        Storyboard.SetTargetProperty(translate, "(UIElement.RenderTransform).(TranslateTransform.X)");

        storyboard.Children.Add(opacity);
        storyboard.Children.Add(translate);
        storyboard.Begin();
    }
}






































































