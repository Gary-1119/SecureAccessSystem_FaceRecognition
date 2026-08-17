using Microsoft.UI.Xaml.Controls;
using SAS.Models;
using SAS.Services;

namespace SAS.Views.Auth;

public sealed class SignInDialog : ContentDialog
{
    private readonly UserAuthService _authService;
    private readonly InfoBar _messageInfoBar;
    private readonly TextBox _ntidTextBox;
    private readonly PasswordBox _passwordBox;

    public AppUser? SignedInUser { get; private set; }

    public SignInDialog(UserAuthService authService)
    {
        _authService = authService;
        Title = _authService.HasAdmins ? "Sign in" : "First admin sign in";
        PrimaryButtonText = "Sign in";
        CloseButtonText = "Cancel";
        DefaultButton = ContentDialogButton.Primary;

        _messageInfoBar = new InfoBar
        {
            IsOpen = false,
            Severity = InfoBarSeverity.Error
        };
        _ntidTextBox = new TextBox
        {
            Header = "NTID",
            PlaceholderText = "Enter NTID"
        };
        _passwordBox = new PasswordBox
        {
            Header = "Password"
        };

        Content = new StackPanel
        {
            Spacing = 12,
            MinWidth = 320,
            Children =
            {
                _messageInfoBar,
                _ntidTextBox,
                _passwordBox
            }
        };

        PrimaryButtonClick += ContentDialog_PrimaryButtonClick;
    }

    private void ContentDialog_PrimaryButtonClick(ContentDialog sender, ContentDialogButtonClickEventArgs args)
    {
        try
        {
            _messageInfoBar.IsOpen = false;
            SignedInUser = _authService.SignIn(_ntidTextBox.Text, _passwordBox.Password);
        }
        catch (Exception ex)
        {
            args.Cancel = true;
            _messageInfoBar.Message = ex.Message;
            _messageInfoBar.IsOpen = true;
        }
    }
}
