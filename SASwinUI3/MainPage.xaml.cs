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
using System.Text.Json.Nodes;
using Windows.Data.Xml.Dom;
using Windows.UI.Notifications;
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
    private readonly PiConnectionController _piConnectionController;
    private readonly FaceDataController? _faceDataController;
    private readonly LogsController _logsController;
    private readonly SettingsController _settingsController;
    private readonly LockFlowController _lockFlowController;
    private readonly DispatcherQueueTimer _clockTimer;
    private readonly DispatcherQueueTimer _countdownTimer;
    private readonly DispatcherQueueTimer _receivedPollTimer;
    private readonly DispatcherQueueTimer _piHealthWatchdogTimer;
    private readonly ObservableCollection<FaceUserListItem> _userRows = [];
    private readonly ObservableCollection<string> _sftpTargets = [];
    private readonly HashSet<string> _receivedSeenFiles = new(StringComparer.OrdinalIgnoreCase);
    private readonly SemaphoreSlim _dialogSemaphore = new(1, 1);

    private AppSettings _settings;
    private PiReconnectWindow? _piReconnectWindow;
    private LockWidgetWindow? _lockWidgetWindow;
    private CancellationTokenSource? _piReconnectCloseCts;
    private bool _suppressPiReconnectPrompt;
    private bool _isConnectingPi;
    private bool _isNavigatingBack;
    private bool _suppressSftpSelectAllChange;
    private bool _receivedPollInitialized;
    private bool _showRecognitionPreview = true;
    private bool _isLoadingSettings;
    private bool _isAutoSavingSettings;
    private int _recognitionPreviewRenderActive;
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
        _log.SetServerMirrorPath(_settings.ServerPath);
        _authService = new UserAuthService();
        _recognitionService = new PiRecognitionService(_log);
        _piConnectionController = new PiConnectionController(_recognitionService, _log);
        var piTransferService = _recognitionService as IPiTransferService;
        _faceDataController = piTransferService is null ? null : new FaceDataController(piTransferService, _log);
        _logsController = new LogsController(_log, piTransferService);
        var runtimeLockService = new RuntimeLockService(DispatcherQueue, _log);
        var lockWidgetService = new LockWidgetService(ShowLockWidgetWindow, CloseLockWidgetWindow, _log);
        _lockFlowController = new LockFlowController(runtimeLockService, lockWidgetService, _recognitionService, _log);
        _settingsController = new SettingsController(_settingsService, _authService, _recognitionService, piTransferService, _lockFlowController, _log);

        RecognitionPage.SetLogItemsSource(_log.Entries);
        LogsPage.SetSasLogItemsSource(_log.Entries);
        LogsPage.SasLogPath = _log.TodayLogPath;
        LogsPage.DownloadSasLogRequested += DownloadSasLogButton_Click;
        LogsPage.RefreshPiLogsRequested += RefreshPiLogsButton_Click;
        LogsPage.DownloadPiLogRequested += DownloadPiLogButton_Click;
        LogsPage.BrowseSasLogFolderRequested += BrowseSasLogFolderButton_Click;
        LogsPage.BrowsePiLogFolderRequested += BrowsePiLogFolderButton_Click;
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

        _receivedPollTimer = DispatcherQueue.CreateTimer();
        _receivedPollTimer.Interval = TimeSpan.FromSeconds(20);
        _receivedPollTimer.Tick += async (_, _) => await PollReceivedFaceDataAsync(manual: false);
        _receivedPollTimer.Start();

        _piHealthWatchdogTimer = DispatcherQueue.CreateTimer();
        _piHealthWatchdogTimer.Interval = TimeSpan.FromSeconds(3);
        _piHealthWatchdogTimer.Tick += (_, _) => CheckPiHealthWatchdog();
        _piHealthWatchdogTimer.Start();

        LoadSettingsToForm();
        SftpTargetsListView.ItemsSource = _sftpTargets;
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
        if (!string.IsNullOrWhiteSpace(_settings.PiHost))
        {
            MinimizeMainWindow();
            return;
        }

        ActivateMainWindow();
        SettingsCameraStatusTextBlock.Text = "Status: Not configured";
        RecognitionPage.ClearPreview("Pi hostname is not configured.");
        _suppressPiReconnectPrompt = true;

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
        await RefreshSftpTargetsAsync(showBusy: false);
        await PollReceivedFaceDataAsync(manual: false);
    }

    private async Task InitializeRecognitionUsersAsync()
    {
        try
        {
            if (string.IsNullOrWhiteSpace(_settings.PiHost))
            {
                await _recognitionService.ConfigureAsync(_settings);
                return;
            }

            _showRecognitionPreview = true;
            DispatcherQueue.TryEnqueue(() =>
            {
                SettingsCameraStatusTextBlock.Text = "Status: Connecting...";
                RecognitionPage.ClearPreview("Connecting to camera...");
            });

            var result = await _piConnectionController.ConnectAsync(
                _settings,
                _ => _settingsController.PushCameraRotationToPiAsync(_settings),
                waitTimeout: TimeSpan.FromSeconds(8));

            DispatcherQueue.TryEnqueue(() =>
            {
                SettingsCameraStatusTextBlock.Text = result.Connected ? "Status: Connected" : "Status: Disconnected";
                if (!result.Connected)
                {
                    RecognitionPage.ClearPreview(result.Message);
                }
            });

            DispatcherQueue.TryEnqueue(RefreshUsers);
        }
        catch (Exception ex)
        {
            _log.Write($"Initial Pi users load failed: {ex.Message}");
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
            CameraSourceComboBox.SelectedIndex = 0;
            WebcamIndexComboBox.SelectedIndex = Math.Clamp(_settings.WebcamIndex, 0, 2);
            var canShowServerCredentials = CanShowServerMountCredentials();
            RtspUserTextBox.Text = canShowServerCredentials ? _settings.ServerUsername : "";
            RtspPasswordBox.Password = canShowServerCredentials ? _settings.ServerPassword : "";
            RtspPortTextBox.Text = "5000";
            RtspPathTextBox.Text = _settings.ServerPath;
            LoadLockTimeoutToForm(_settings.LockTimeoutSeconds);
            DisableKeyboardToggle.IsOn = _settings.DisableKeyboardWhenLocked;
            DisableMouseToggle.IsOn = _settings.DisableMouseWhenLocked;
            TransportComboBox.SelectedIndex = string.Equals(_settings.Transport, "udp", StringComparison.OrdinalIgnoreCase) ? 1 : 0;
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
        _settings.CameraSource = "pi";
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
        _settings.RtspUser = _settings.ServerUsername;
        _settings.RtspPassword = _settings.ServerPassword;
        _settings.RtspPort = _settings.ApiPort;
        _settings.RtspPath = _settings.ServerPath;
        _settings.Transport = TransportComboBox.SelectedIndex == 1 ? "udp" : "tcp";
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
            () => _piConnectionController.StartForLockAsync(_settings),
            UpdateLockUi);
    }

    private void UnlockSystem(string reason)
    {
        _lockFlowController.Unlock(_settings, reason, ResetInactivityCountdown, ClosePiReconnectPrompt, UpdateLockUi);
    }

    private void EmergencyUnlock()
    {
        _log.WriteAudit("EMERGENCY UNLOCK", "Method=Emergency hotkey");
        UnlockSystem("Emergency hotkey");
        FaceStateTextBlock.Text = "Desktop input released; restricted pages still require normal authorization.";
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
            var connectionLabel = PiConnectionController.GetConnectionLabel(status);
            SettingsCameraStatusTextBlock.Text = $"Status: {connectionLabel}";
            RecognitionPage.SetCameraState(connectionLabel);
            HandlePiConnectionStatus(status);
            if (_showRecognitionPreview && !PiConnectionController.IsEffectivelyConnected(status))
            {
                var message = string.IsNullOrWhiteSpace(status.LastError)
                    ? $"Camera state: {connectionLabel}"
                    : status.LastError;
                RecognitionPage.ClearPreview(message);
            }
        });
    }

    private void HandlePiConnectionStatus(RecognitionStatus status)
    {
        var connected = PiConnectionController.IsEffectivelyConnected(status);
        if (_suppressPiReconnectPrompt && !connected)
        {
            return;
        }

        if (connected)
        {
            _suppressPiReconnectPrompt = false;
        }

        if (PiConnectionController.IsDisconnectedForPrompt(status))
        {
            ShowPiReconnectPrompt(status);
            return;
        }

        if (connected && _piReconnectWindow is not null && PiConnectionController.HasRecentPreviewFrame(status))
        {
            ShowPiReconnectedThenClose();
        }

        if (!status.IsRunning && _piReconnectWindow is not null)
        {
            ClosePiReconnectPrompt();
        }
    }

    private void CheckPiHealthWatchdog()
    {
        if (string.IsNullOrWhiteSpace(_settings.PiHost) || !_recognitionService.CurrentStatus.IsRunning)
        {
            return;
        }

        var status = _recognitionService.CurrentStatus;
        var hasRecentPreview = PiConnectionController.HasRecentPreviewFrame(status);
        var isExplicitlyDisconnected = status.ConnectionState.Contains("disconnect", StringComparison.OrdinalIgnoreCase) ||
            status.ConnectionState.Contains("reconnect", StringComparison.OrdinalIgnoreCase);
        var previewHasStartedBefore = status.LastFrameAt is not null;
        var stalePreview = previewHasStartedBefore && !hasRecentPreview;

        if (!isExplicitlyDisconnected && !stalePreview)
        {
            return;
        }

        var message = string.IsNullOrWhiteSpace(status.LastError)
            ? stalePreview
                ? "Camera preview stopped updating. Checking Pi connection..."
                : "Pi connection interrupted."
            : status.LastError;
        var promptStatus = status with
        {
            StreamHealthy = false,
            ConnectionState = "disconnected",
            LastError = message
        };

        if (_lockFlowController.IsLocked)
        {
            _suppressPiReconnectPrompt = false;
        }

        HandlePiConnectionStatus(promptStatus);
    }

    private void ShowPiReconnectPrompt(RecognitionStatus status)
    {
        _piReconnectCloseCts?.Cancel();
        _piReconnectCloseCts?.Dispose();
        _piReconnectCloseCts = null;

        var hostname = string.IsNullOrWhiteSpace(_settings.PiHost) ? _settings.CameraHost : _settings.PiHost;
        if (_piReconnectWindow is null)
        {
            _piReconnectWindow = new PiReconnectWindow(hostname, _lockFlowController.IsLocked);
            _piReconnectWindow.Closed += (_, _) => _piReconnectWindow = null;
            _piReconnectWindow.RetryRequested += PiReconnectWindow_RetryRequested;
            _piReconnectWindow.ChangeHostnameRequested += PiReconnectWindow_ChangeHostnameRequested;
            _piReconnectWindow.DismissRequested += PiReconnectWindow_DismissRequested;
            _piReconnectWindow.Activate();
            _log.Write($"Pi disconnect prompt opened for {hostname}.");
        }

        _piReconnectWindow.ShowDisconnected(hostname, status.LastError, _lockFlowController.IsLocked);
        _piReconnectWindow.Activate();
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

    private void CloseLockWidgetWindow()
    {
        var window = _lockWidgetWindow;
        _lockWidgetWindow = null;
        window?.Close();
    }

    private async void PiReconnectWindow_RetryRequested(object? sender, EventArgs e)
    {
        await RetryPiConnectionAsync();
    }

    private async void PiReconnectWindow_ChangeHostnameRequested(object? sender, EventArgs e)
    {
        _suppressPiReconnectPrompt = true;
        ClosePiReconnectPrompt();
        ActivateMainWindow();

        if (!AppSession.IsAdmin && !await ShowSignInDialogAsync())
        {
            return;
        }

        if (!AppSession.IsAdmin)
        {
            await ShowInfoDialogAsync("Admin required", "Only an admin can change the Pi hostname.");
            return;
        }

        if (_lockFlowController.IsLocked)
        {
            _log.WriteAudit("ADMIN EMERGENCY UNLOCK", "Method=Admin hostname change");
            UnlockSystem("Admin hostname change");
        }

        NavigateToHostnameSettings();
    }

    private void PiReconnectWindow_DismissRequested(object? sender, EventArgs e)
    {
        if (_lockFlowController.IsLocked &&
            sender is not PiReconnectWindow { IsConnectedState: true })
        {
            return;
        }

        _suppressPiReconnectPrompt = true;
        ClosePiReconnectPrompt();
    }

    private async Task RetryPiConnectionAsync()
    {
        try
        {
            _suppressPiReconnectPrompt = false;
            ReadSettingsFromForm();
            _log.SetServerMirrorPath(_settings.ServerPath);
            _settingsService.Save(_settings);
            await _piConnectionController.RetryAsync(_settings, _ => _settingsController.PushCameraRotationToPiAsync(_settings));
        }
        catch (Exception ex)
        {
            _log.Write($"Pi reconnect retry failed: {ex.Message}");
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

    private void ShowPiReconnectedThenClose()
    {
        var window = _piReconnectWindow;
        if (window is null)
        {
            return;
        }

        _piReconnectCloseCts?.Cancel();
        _piReconnectCloseCts?.Dispose();
        _piReconnectCloseCts = new CancellationTokenSource();
        var token = _piReconnectCloseCts.Token;

        window.ShowConnected(_lockFlowController.IsLocked);
        window.Activate();
        _ = ClosePiReconnectPromptAfterDelayAsync(token);
    }

    private async Task ClosePiReconnectPromptAfterDelayAsync(CancellationToken cancellationToken)
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
            _log.Write("Pi reconnect prompt auto-closed after reconnect.");
            ClosePiReconnectPrompt();
        });
    }

    private void ClosePiReconnectPrompt()
    {
        _piReconnectCloseCts?.Cancel();
        _piReconnectCloseCts?.Dispose();
        _piReconnectCloseCts = null;

        var window = _piReconnectWindow;
        if (window is not null)
        {
            window.RetryRequested -= PiReconnectWindow_RetryRequested;
            window.ChangeHostnameRequested -= PiReconnectWindow_ChangeHostnameRequested;
            window.DismissRequested -= PiReconnectWindow_DismissRequested;
        }
        _piReconnectWindow = null;
        window?.Close();
    }

    private void RecognitionService_PreviewFrameAvailable(object? sender, PreviewFrame frame)
    {
        _pendingRecognitionPreviewFrame = frame;
        if (Interlocked.Exchange(ref _recognitionPreviewRenderActive, 1) != 0)
        {
            return;
        }

        DispatcherQueue.TryEnqueue(async () => await DrainRecognitionPreviewFramesAsync());
    }

    private async Task DrainRecognitionPreviewFramesAsync()
    {
        try
        {
            while (_pendingRecognitionPreviewFrame is { } frame)
            {
                _pendingRecognitionPreviewFrame = null;
                if (!_showRecognitionPreview)
                {
                    continue;
                }

                var wait = RecognitionPreviewMinInterval - (DateTimeOffset.Now - _lastRecognitionPreviewRenderAt);
                if (wait > TimeSpan.Zero)
                {
                    await Task.Delay(wait);
                }

                await RenderRecognitionPreviewFrameAsync(frame);
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

    private async Task RenderRecognitionPreviewFrameAsync(PreviewFrame frame)
    {
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
        _log.SetServerMirrorPath(_settings.ServerPath);
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
            _log.SetServerMirrorPath(_settings.ServerPath);
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
        if (_isConnectingPi)
        {
            return;
        }

        _isConnectingPi = true;
        _suppressPiReconnectPrompt = false;
        _showRecognitionPreview = true;
        RecognitionPage.ClearPreview("Connecting to camera...");
        ConnectPiButton.IsEnabled = false;
        ConnectPiProgressRing.IsActive = true;
        ConnectPiProgressRing.Visibility = Visibility.Visible;
        SettingsCameraStatusTextBlock.Text = "Status: Connecting...";
        ReadSettingsFromForm();
        _settingsService.Save(_settings);
        try
        {
            var result = await _piConnectionController.ConnectAsync(
                _settings,
                _ => _settingsController.PushCameraRotationToPiAsync(_settings),
                RefreshUsers,
                TimeSpan.FromSeconds(6));
            if (result.Connected)
            {
                SettingsCameraStatusTextBlock.Text = "Status: Connected";
                await ShowInfoDialogAsync("Pi connected", $"Connected to {_settings.PiHost}.");
            }
            else
            {
                SettingsCameraStatusTextBlock.Text = "Status: Disconnected";
                HandlePiConnectionStatus(result.Status);
                var title = PiConnectionController.IsAlreadyConnectedByAnotherSas(result.Message)
                    ? "Pi already in use"
                    : "Pi connection failed";
                await ShowInfoDialogAsync(title, result.Message);
            }
        }
        catch (Exception ex)
        {
            SettingsCameraStatusTextBlock.Text = "Status: Disconnected";
            HandlePiConnectionStatus(_recognitionService.CurrentStatus);
            await ShowInfoDialogAsync("Pi connection failed", ex.Message);
        }
        finally
        {
            ConnectPiProgressRing.IsActive = false;
            ConnectPiProgressRing.Visibility = Visibility.Collapsed;
            ConnectPiButton.IsEnabled = true;
            _isConnectingPi = false;
        }
    }

    private void StopRecognitionButton_Click(object sender, RoutedEventArgs e)
    {
        _showRecognitionPreview = false;
        RecognitionPage.ClearPreview("Camera view is closed. Pi recognition is still running.");
        _log.Write("Recognition camera view closed by user; Pi recognition remains running.");
    }

    private async void OpenCameraButton_Click(object sender, RoutedEventArgs e)
    {
        _suppressPiReconnectPrompt = false;
        _showRecognitionPreview = true;
        ReadSettingsFromForm();
        _settings.CameraSource = "pi";
        _settingsService.Save(_settings);
        RecognitionPage.ShowPreviewMessage("Opening camera view...");
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
        RecognitionPage.ClearPreview("Camera view is closed. Press Open Camera to view again.");
        _log.Write("Face Recognition camera view closed by user; Pi recognition remains running.");
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
        var serverImportZipPath = importZipPath;
        if (!importLocal)
        {
            importZipPath = FaceDataController.NormalizeServerPath(importZipPath);
            serverImportZipPath = FaceDataController.GetMountedServerZipPath(importZipPath);
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

        SetFaceDataOperationState(true, importLocal ? "Uploading local ZIP to Pi..." : "Importing server ZIP on Pi...");
        try
        {
            var added = await _faceDataController.ImportAsync(new FaceDataImportRequest(importLocal, importZipPath, serverImportZipPath, serverCredentials));
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




    private async void RestoreFaceDataBackupButton_Click(object sender, RoutedEventArgs e)
    {
        if (_faceDataController is null)
        {
            return;
        }

        SetFaceDataOperationState(true, "Checking received face data...");
        try
        {
            await PollReceivedFaceDataAsync(manual: true);
        }
        catch (Exception ex)
        {
            _log.Write($"Check received failed: {ex}");
            ShowFaceDataMessage("Check received failed", ex.Message, InfoBarSeverity.Error);
        }
        finally
        {
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
        RestoreFaceDataBackupButton.IsEnabled = !isRunning;
        AddSftpTargetButton.IsEnabled = !isRunning;
        RefreshSftpTargetsButton.IsEnabled = !isRunning;
        RefreshPiStorageButton.IsEnabled = !isRunning;
        SendSftpTargetsButton.IsEnabled = !isRunning;
        RemoveSftpTargetButton.IsEnabled = !isRunning;
        SftpTargetTextBox.IsEnabled = !isRunning;
        SftpTargetsListView.IsEnabled = !isRunning;
        SelectAllSftpTargetsCheckBox.IsEnabled = !isRunning;

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

    private async Task<string?> PickLogDestinationFolderAsync()
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
        var folder = await PickLogDestinationFolderAsync();
        if (!string.IsNullOrWhiteSpace(folder))
        {
            LogsPage.SasDestinationFolder = folder;
        }
    }

    private async void BrowsePiLogFolderButton_Click(object sender, RoutedEventArgs e)
    {
        var folder = await PickLogDestinationFolderAsync();
        if (!string.IsNullOrWhiteSpace(folder))
        {
            LogsPage.PiDestinationFolder = folder;
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

    private async void RefreshPiLogsButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshPiLogsAsync(showSuccess: true);
    }

    private async Task<IReadOnlyList<string>> RefreshPiLogsAsync(bool showSuccess)
    {
        SetLogsOperationState(true, "Loading Pi logs...");
        try
        {
            await SyncPiApiToSettingsFormAsync(save: false);
            var lines = await _logsController.RefreshPiLogsAsync(_settings);
            LogsPage.PiLogPreview = lines.Count == 0
                ? "No Pi logs returned."
                : string.Join(Environment.NewLine, lines);
            LogsPage.PiLogStatus = $"{lines.Count} Pi log line{(lines.Count == 1 ? "" : "s")} loaded.";
            if (showSuccess)
            {
                ShowLogsMessage("Pi logs loaded", LogsPage.PiLogStatus, InfoBarSeverity.Success);
            }

            return lines;
        }
        catch (Exception ex)
        {
            LogsPage.PiLogStatus = "Pi logs could not be loaded.";
            _log.Write($"Pi log refresh failed: {ex.Message}");
            ShowLogsMessage("Pi log refresh failed", ex.Message, InfoBarSeverity.Error);
            return [];
        }
        finally
        {
            SetLogsOperationState(false);
        }
    }

    private async void DownloadPiLogButton_Click(object sender, RoutedEventArgs e)
    {
        SetLogsOperationState(true, "Preparing Pi log download...");
        try
        {
            await SyncPiApiToSettingsFormAsync(save: false);
            var result = await _logsController.DownloadPiLogAsync(_settings, LogsPage.PiDestinationFolder);
            LogsPage.PiLogPreview = result.Lines.Count == 0
                ? "No Pi logs returned."
                : string.Join(Environment.NewLine, result.Lines);
            LogsPage.PiLogStatus = $"{result.Lines.Count} Pi log line{(result.Lines.Count == 1 ? "" : "s")} loaded.";
            ShowLogsMessage("Pi log downloaded", $"Saved to {result.Path}", InfoBarSeverity.Success);
        }
        catch (Exception ex)
        {
            _log.Write($"Pi log download failed: {ex.Message}");
            ShowLogsMessage("Pi log download failed", ex.Message, InfoBarSeverity.Error);
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
        RtspPortTextBox.IsEnabled = true;
        RtspUserTextBox.IsEnabled = true;
        RtspPasswordBox.IsEnabled = true;
        RtspPathTextBox.IsEnabled = true;
        SelectServerMountPathButton.IsEnabled = true;
        SettingsCameraStatusTextBlock.Text = string.IsNullOrWhiteSpace(CameraHostTextBox.Text)
            ? "Status: Disconnected"
            : $"Status: {PiConnectionController.GetConnectionLabel(_recognitionService.CurrentStatus)}";
    }

    private async void MountServerButton_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            ReadSettingsFromForm();
            _log.SetServerMirrorPath(_settings.ServerPath);
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
                    ? "The Pi accepted the server mount settings."
                    : "Server mount details are blank, so nothing was sent to the Pi.");
        }
        catch (Exception ex)
        {
            _log.Write($"Server mount failed: {ex.Message}");
            await ShowInfoDialogAsync("Server mount failed", ex.Message);
        }
    }

    private async void RefreshSftpTargetsButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshSftpTargetsAsync();
    }

    private async void RefreshPiStorageButton_Click(object sender, RoutedEventArgs e)
    {
        await RefreshPiStorageAsync(manual: true);
    }

    private async Task RefreshPiStorageAsync(bool manual)
    {
        if (_faceDataController is null)
        {
            return;
        }

        try
        {
            if (manual)
            {
                await SyncPiApiToSettingsFormAsync(save: false);
            }

            var storage = await _faceDataController.GetStorageInfoAsync();
            UpdatePiStorage(storage);
        }
        catch (Exception ex)
        {
            PiStorageStatusTextBlock.Text = "Unavailable";
            PiStorageProgressBar.Value = 0;
            if (manual)
            {
                ShowFaceDataMessage("Storage refresh failed", ex.Message, InfoBarSeverity.Error);
            }
        }
    }

    private void UpdatePiStorage(PiStorageInfo storage)
    {
        PiStorageProgressBar.Value = storage.UsedPercent;
        PiStorageStatusTextBlock.Text = storage.TotalBytes > 0
            ? $"{storage.Label} ({storage.UsedPercent:0}% used)"
            : storage.Label;
    }

    private async Task RefreshSftpTargetsAsync(bool showBusy = true)
    {
        if (_faceDataController is null)
        {
            return;
        }

        if (showBusy)
        {
            SetFaceDataOperationState(true, "Loading SFTP targets...");
        }

        try
        {
            await SyncPiApiToSettingsFormAsync(save: false);
            var targets = await _faceDataController.ListSftpTargetsAsync();
            _sftpTargets.Clear();
            foreach (var target in targets)
            {
                _sftpTargets.Add(target);
            }

            UpdateSftpSelectAllState();
            if (showBusy)
            {
                ShowFaceDataMessage("Targets loaded", "SFTP target list refreshed from the Pi.", InfoBarSeverity.Success);
            }
        }
        catch (Exception ex)
        {
            if (showBusy)
            {
                ShowFaceDataMessage("Targets not loaded", ex.Message, InfoBarSeverity.Error);
            }
        }
        finally
        {
            if (showBusy)
            {
                SetFaceDataOperationState(false);
            }
        }
    }

    private async void AddSftpTargetButton_Click(object sender, RoutedEventArgs e)
    {
        if (_faceDataController is null)
        {
            return;
        }

        var host = SftpTargetTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(host))
        {
            ShowFaceDataMessage("Target required", "Enter a target hostname or IP address.", InfoBarSeverity.Warning);
            return;
        }

        SetFaceDataOperationState(true, "Adding SFTP target...");
        try
        {
            await SyncPiApiToSettingsFormAsync(save: false);
            await _faceDataController.AddSftpTargetAsync(host);
            SftpTargetTextBox.Text = "";
            await RefreshSftpTargetsAsync(showBusy: false);
            ShowFaceDataMessage("Target added", $"{host} was added. Online/offline state is checked during transfer.", InfoBarSeverity.Success);
        }
        catch (Exception ex)
        {
            ShowFaceDataMessage("Target not added", ex.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SetFaceDataOperationState(false);
        }
    }

    private async void RemoveSftpTargetButton_Click(object sender, RoutedEventArgs e)
    {
        if (_faceDataController is null)
        {
            return;
        }

        var targets = SftpTargetsListView.SelectedItems.Cast<string>().ToList();
        if (targets.Count == 0)
        {
            ShowFaceDataMessage("No target selected", "Select one or more targets to remove.", InfoBarSeverity.Warning);
            return;
        }

        if (!await ConfirmActionAsync("Remove selected targets?", $"Remove {targets.Count} SFTP target{(targets.Count == 1 ? "" : "s")} from the Pi list?", "Remove"))
        {
            return;
        }

        SetFaceDataOperationState(true, "Removing SFTP targets...");
        try
        {
            await SyncPiApiToSettingsFormAsync(save: false);
            await _faceDataController.RemoveSftpTargetsAsync(targets);
            await RefreshSftpTargetsAsync(showBusy: false);
            ShowFaceDataMessage("Targets removed", $"{targets.Count} target{(targets.Count == 1 ? "" : "s")} removed.", InfoBarSeverity.Success);
        }
        catch (Exception ex)
        {
            ShowFaceDataMessage("Targets not removed", ex.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SetFaceDataOperationState(false);
        }
    }

    private async void SendSftpTargetsButton_Click(object sender, RoutedEventArgs e)
    {
        if (_faceDataController is null)
        {
            return;
        }

        var targets = SftpTargetsListView.SelectedItems.Cast<string>().ToList();
        if (targets.Count == 0)
        {
            ShowFaceDataMessage("No target selected", "Select one or more targets to receive face data.", InfoBarSeverity.Warning);
            return;
        }

        SetFaceDataOperationState(true, "Starting multi-Pi transfer...");
        try
        {
            await SyncPiApiToSettingsFormAsync(save: false);
            var batchId = await _faceDataController.StartSftpTransferAsync(targets);
            ShowFaceDataMessage("Transfer started", $"Batch {batchId} started for {targets.Count} target{(targets.Count == 1 ? "" : "s")}.", InfoBarSeverity.Success);
            await ShowSftpTransferProgressDialogAsync(batchId);
        }
        catch (Exception ex)
        {
            ShowFaceDataMessage("Transfer failed", ex.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SetFaceDataOperationState(false);
        }
    }

    private void SelectAllSftpTargetsCheckBox_Changed(object sender, RoutedEventArgs e)
    {
        if (_suppressSftpSelectAllChange)
        {
            return;
        }

        if (SelectAllSftpTargetsCheckBox.IsChecked == true)
        {
            SftpTargetsListView.SelectAll();
            return;
        }

        SftpTargetsListView.SelectedItems.Clear();
    }

    private void SftpTargetsListView_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        UpdateSftpSelectAllState();
    }

    private void UpdateSftpSelectAllState()
    {
        if (SelectAllSftpTargetsCheckBox is null || SftpTargetsListView is null)
        {
            return;
        }

        _suppressSftpSelectAllChange = true;
        SelectAllSftpTargetsCheckBox.IsChecked = _sftpTargets.Count > 0 && SftpTargetsListView.SelectedItems.Count == _sftpTargets.Count;
        _suppressSftpSelectAllChange = false;
    }

    private async Task ShowSftpTransferProgressDialogAsync(string batchId)
    {
        if (_faceDataController is null)
        {
            return;
        }

        var jobs = new ObservableCollection<SftpTransferJobItem>();
        var summaryText = new TextBlock
        {
            Text = "Preparing transfer...",
            Style = (Style)Resources["SmallLabelStyle"],
            Margin = new Thickness(0, 0, 0, 10)
        };
        var list = new ListView
        {
            ItemsSource = jobs,
            SelectionMode = ListViewSelectionMode.None,
            Height = Math.Clamp(ActualHeight - 380, 260, 520),
            ItemTemplate = CreateSftpTransferJobTemplate()
        };
        var content = new StackPanel();
        content.Children.Add(summaryText);
        content.Children.Add(list);

        var dialog = new ContentDialog
        {
            Title = "SFTP transfer progress",
            Content = content,
            PrimaryButtonText = "Cancel transfer",
            CloseButtonText = "Close",
            DefaultButton = ContentDialogButton.Close,
            XamlRoot = XamlRoot
        };

        var timer = DispatcherQueue.CreateTimer();
        timer.Interval = TimeSpan.FromSeconds(1);

        async Task RefreshAsync()
        {
            try
            {
                var data = await _faceDataController.GetSftpTransferAsync(batchId);
                var batch = data["batch"] as JsonObject ?? data;
                var summary = batch["summary"] as JsonObject ?? new JsonObject();
                var state = ReadJsonString(batch, "state");
                var running = ReadJsonBool(batch, "running");
                summaryText.Text = $"{state}  |  {ReadJsonInt(summary, "success")} success  |  {ReadJsonInt(summary, "failed")} failed  |  {ReadJsonInt(summary, "active")} active  |  {ReadJsonInt(summary, "waiting")} waiting";

                jobs.Clear();
                if (batch["jobs"] is JsonArray jobArray)
                {
                    foreach (var node in jobArray.OfType<JsonObject>())
                    {
                        jobs.Add(new SftpTransferJobItem
                        {
                            Hostname = ReadJsonString(node, "hostname"),
                            Status = ReadJsonString(node, "status"),
                            Message = ReadJsonString(node, "message"),
                            Progress = Math.Clamp(ReadJsonInt(node, "progress"), 0, 100)
                        });
                    }
                }

                dialog.IsPrimaryButtonEnabled = running;
                if (!running)
                {
                    timer.Stop();
                }
            }
            catch (Exception ex)
            {
                summaryText.Text = $"Could not refresh transfer status: {ex.Message}";
            }
        }

        timer.Tick += async (_, _) => await RefreshAsync();
        dialog.PrimaryButtonClick += async (_, args) =>
        {
            args.Cancel = true;
            try
            {
                await _faceDataController.CancelSftpTransferAsync(batchId);
                summaryText.Text = "Cancellation requested. Active uploads will stop at the next Pi progress update.";
                await RefreshAsync();
            }
            catch (Exception ex)
            {
                summaryText.Text = ex.Message;
            }
        };

        await RefreshAsync();
        timer.Start();
        await dialog.ShowAsync();
        timer.Stop();
    }

    private static DataTemplate CreateSftpTransferJobTemplate()
    {
        return (DataTemplate)XamlReader.Load(
            """
            <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
                <Grid Padding="0,10" ColumnSpacing="12">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="160" />
                        <ColumnDefinition Width="*" />
                        <ColumnDefinition Width="64" />
                    </Grid.ColumnDefinitions>
                    <TextBlock Text="{Binding Hostname}" FontWeight="SemiBold" TextTrimming="CharacterEllipsis" VerticalAlignment="Center" />
                    <StackPanel Grid.Column="1" Spacing="5">
                        <TextBlock Text="{Binding Status}" FontWeight="SemiBold" />
                        <ProgressBar Minimum="0" Maximum="100" Value="{Binding Progress}" />
                        <TextBlock Text="{Binding Message}" FontSize="12" Foreground="{ThemeResource TextFillColorSecondaryBrush}" TextWrapping="Wrap" />
                    </StackPanel>
                    <TextBlock Grid.Column="2" Text="{Binding ProgressText}" FontWeight="SemiBold" HorizontalAlignment="Right" VerticalAlignment="Center" />
                </Grid>
            </DataTemplate>
            """);
    }

    private static string ReadJsonString(JsonObject data, string key)
    {
        return data.TryGetPropertyValue(key, out var node) && node is JsonValue value && value.TryGetValue<string>(out var text)
            ? text ?? ""
            : "";
    }

    private static int ReadJsonInt(JsonObject data, string key)
    {
        if (!data.TryGetPropertyValue(key, out var node) || node is not JsonValue value)
        {
            return 0;
        }

        if (value.TryGetValue<int>(out var integer))
        {
            return integer;
        }

        return value.TryGetValue<string>(out var text) && int.TryParse(text, out var parsed) ? parsed : 0;
    }

    private static bool ReadJsonBool(JsonObject data, string key)
    {
        if (!data.TryGetPropertyValue(key, out var node) || node is not JsonValue value)
        {
            return false;
        }

        if (value.TryGetValue<bool>(out var boolean))
        {
            return boolean;
        }

        return value.TryGetValue<string>(out var text) && bool.TryParse(text, out var parsed) && parsed;
    }

    private async Task ShowReceivedFaceDataDialogAsync(IReadOnlyList<string> pending)
    {
        if (_faceDataController is null)
        {
            return;
        }

        var list = new ListView
        {
            ItemsSource = pending,
            SelectionMode = ListViewSelectionMode.Single,
            Height = Math.Clamp(ActualHeight - 360, 220, 420)
        };

        var dialog = new ContentDialog
        {
            Title = pending.Count == 0 ? "No pending received data" : "Pending received face data",
            Content = pending.Count == 0 ? "No ZIP packages are waiting for review on the Pi." : list,
            PrimaryButtonText = pending.Count == 0 ? "" : "Accept",
            SecondaryButtonText = pending.Count == 0 ? "" : "Reject",
            CloseButtonText = "Close",
            DefaultButton = ContentDialogButton.Close,
            XamlRoot = XamlRoot
        };

        var result = await dialog.ShowAsync();
        if (pending.Count == 0 || list.SelectedItem is not string filename)
        {
            return;
        }

        SetFaceDataOperationState(true, result == ContentDialogResult.Primary ? "Accepting received package..." : "Rejecting received package...");
        try
        {
            if (result == ContentDialogResult.Primary)
            {
                var imported = await _faceDataController.AcceptReceivedAsync(filename);
                RefreshUsers();
                await RefreshPiStorageAsync(manual: false);
                ShowFaceDataMessage("Received data imported", $"{filename} accepted. {imported} user{(imported == 1 ? "" : "s")} imported.", InfoBarSeverity.Success);
            }
            else if (result == ContentDialogResult.Secondary)
            {
                await _faceDataController.RejectReceivedAsync(filename);
                await RefreshPiStorageAsync(manual: false);
                ShowFaceDataMessage("Received data rejected", $"{filename} rejected.", InfoBarSeverity.Success);
            }
        }
        catch (Exception ex)
        {
            ShowFaceDataMessage("Received action failed", ex.Message, InfoBarSeverity.Error);
        }
        finally
        {
            SetFaceDataOperationState(false);
        }
    }

    private async Task PollReceivedFaceDataAsync(bool manual)
    {
        if (_faceDataController is null)
        {
            return;
        }

        try
        {
            if (manual)
            {
                await SyncPiApiToSettingsFormAsync(save: false);
            }

            var pending = await _faceDataController.ListReceivedAsync();
            UpdateReceivedBadge(pending.Count);
            await RefreshPiStorageAsync(manual: false);

            var current = pending.ToHashSet(StringComparer.OrdinalIgnoreCase);
            if (!_receivedPollInitialized)
            {
                _receivedSeenFiles.Clear();
                foreach (var file in current)
                {
                    _receivedSeenFiles.Add(file);
                }

                _receivedPollInitialized = true;
                if (pending.Count > 0)
                {
                    ShowReceivedToast(pending);
                    _log.Write($"Received face data pending: {string.Join(", ", pending)}");
                }

                return;
            }

            var newFiles = pending.Where(file => !_receivedSeenFiles.Contains(file)).ToList();
            _receivedSeenFiles.Clear();
            foreach (var file in current)
            {
                _receivedSeenFiles.Add(file);
            }

            if (newFiles.Count > 0)
            {
                ShowReceivedToast(newFiles);
                _log.Write($"Received face data pending: {string.Join(", ", newFiles)}");
            }

            if (manual)
            {
                await ShowReceivedFaceDataDialogAsync(pending);
            }
        }
        catch (Exception ex)
        {
            if (manual)
            {
                ShowFaceDataMessage("Check received failed", ex.Message, InfoBarSeverity.Error);
            }
        }
    }

    private void UpdateReceivedBadge(int count)
    {
        if (ReceivedBadgeBorder is null || ReceivedBadgeTextBlock is null)
        {
            return;
        }

        if (count <= 0)
        {
            ReceivedBadgeBorder.Visibility = Visibility.Collapsed;
            ReceivedBadgeTextBlock.Text = "0";
            return;
        }

        var text = count > 99 ? "99+" : count.ToString();
        ReceivedBadgeTextBlock.Text = text;
        ReceivedBadgeBorder.Width = text.Length > 2 ? 32 : 22;
        ReceivedBadgeBorder.Visibility = Visibility.Visible;
    }

    private void ShowReceivedToast(IReadOnlyList<string> newFiles)
    {
        try
        {
            var title = "New received face data";
            var message = newFiles.Count == 1
                ? $"{newFiles[0]} is waiting for review."
                : $"{newFiles.Count} ZIP packages are waiting for review.";
            var logoPath = Path.Combine(AppContext.BaseDirectory, "Assets", "SasLogo.png");
            var imageXml = File.Exists(logoPath)
                ? $"""<image placement="appLogoOverride" src="{SecurityElementEscape("file:///" + logoPath.Replace("\\", "/").Replace(" ", "%20"))}" />"""
                : "";

            var xml = $"""
                <toast scenario="default" launch="sas://face-data/received">
                  <visual>
                    <binding template="ToastGeneric">
                      {imageXml}
                      <text>{SecurityElementEscape(title)}</text>
                      <text>{SecurityElementEscape(message)}</text>
                    </binding>
                  </visual>
                  <audio src="ms-winsoundevent:Notification.Default" />
                </toast>
                """;

            var doc = new XmlDocument();
            doc.LoadXml(xml);
            var notification = new ToastNotification(doc)
            {
                Group = "SAS",
                Tag = "received-face-data"
            };

            try
            {
                ToastNotificationManager.CreateToastNotifier().Show(notification);
            }
            catch
            {
                ToastNotificationManager.CreateToastNotifier("Secure.Access.System").Show(notification);
            }
        }
        catch (Exception ex)
        {
            _log.Write($"Received toast failed: {ex.Message}");
        }
    }

    private static string SecurityElementEscape(string value)
    {
        return System.Security.SecurityElement.Escape(value) ?? "";
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
        _suppressPiReconnectPrompt = false;
        HandlePiConnectionStatus(_recognitionService.CurrentStatus);
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

public sealed class SftpTransferJobItem
{
    public string Hostname { get; set; } = "";
    public string Status { get; set; } = "";
    public string Message { get; set; } = "";
    public int Progress { get; set; }
    public string ProgressText => $"{Progress}%";
}















































































