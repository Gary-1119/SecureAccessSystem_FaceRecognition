using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using SAS.Models;
using SAS.Services;

namespace SAS.Views.Auth;

public sealed class EmergencyAdminUnlockDialog : ContentDialog
{
    private readonly UserAuthService _authService;
    private readonly InfoBar _messageInfoBar;
    private readonly TextBox _ntidTextBox;
    private readonly PasswordBox _passwordBox;
    private int _failedAttempts;

    public AppUser? SignedInAdmin { get; private set; }
    public event EventHandler<EmergencyAdminUnlockFailedEvent>? ValidationFailed;

    public EmergencyAdminUnlockDialog(UserAuthService authService)
    {
        _authService = authService;
        Title = "Admin unlock required";
        PrimaryButtonText = "Unlock";
        DefaultButton = ContentDialogButton.Primary;

        _messageInfoBar = new InfoBar
        {
            IsOpen = true,
            Severity = InfoBarSeverity.Warning,
            Title = "Emergency hotkey pressed",
            Message = "Enter administrator NTID and password to release this locked session."
        };
        _ntidTextBox = new TextBox
        {
            Header = "Admin NTID",
            PlaceholderText = "Enter admin NTID"
        };
        _passwordBox = new PasswordBox
        {
            Header = "Password"
        };

        Content = new StackPanel
        {
            Spacing = 12,
            MinWidth = 360,
            Children =
            {
                _messageInfoBar,
                _ntidTextBox,
                _passwordBox
            }
        };

        PrimaryButtonClick += ContentDialog_PrimaryButtonClick;
        Closing += EmergencyAdminUnlockDialog_Closing;
        Loaded += EmergencyAdminUnlockDialog_Loaded;
    }

    private void EmergencyAdminUnlockDialog_Loaded(object sender, RoutedEventArgs e)
    {
        _ntidTextBox.Focus(FocusState.Programmatic);
    }

    private void ContentDialog_PrimaryButtonClick(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        try
        {
            var user = _authService.SignIn(_ntidTextBox.Text, _passwordBox.Password);
            if (!user.IsAdmin)
            {
                throw new UnauthorizedAccessException("Only SAS administrators can use emergency unlock.");
            }

            SignedInAdmin = user;
        }
        catch (Exception ex)
        {
            _failedAttempts++;
            args.Cancel = true;
            ValidationFailed?.Invoke(this, new EmergencyAdminUnlockFailedEvent(
                (_ntidTextBox.Text ?? "").Trim().ToUpperInvariant(),
                _failedAttempts,
                ex.Message));
            _passwordBox.Password = "";
            _messageInfoBar.Severity = InfoBarSeverity.Error;
            _messageInfoBar.Title = $"Admin validation failed ({_failedAttempts})";
            _messageInfoBar.Message = ex.Message;
            _messageInfoBar.IsOpen = true;
            _passwordBox.Focus(FocusState.Programmatic);
        }
    }

    private void EmergencyAdminUnlockDialog_Closing(ContentDialog sender, ContentDialogClosingEventArgs args)
    {
        if (SignedInAdmin is not null)
        {
            return;
        }

        args.Cancel = true;
        _messageInfoBar.Severity = InfoBarSeverity.Warning;
        _messageInfoBar.Title = "Admin unlock required";
        _messageInfoBar.Message = "This emergency unlock prompt must stay open until a SAS administrator signs in.";
        _messageInfoBar.IsOpen = true;
    }
}

public sealed record EmergencyAdminUnlockFailedEvent(string Ntid, int Attempt, string Message);
