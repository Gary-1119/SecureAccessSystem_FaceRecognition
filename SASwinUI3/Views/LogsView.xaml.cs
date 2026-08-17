using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Collections;

namespace SAS.Views;

public sealed partial class LogsView : UserControl
{
    public event RoutedEventHandler? DownloadSasLogRequested;
    public event RoutedEventHandler? RefreshPiLogsRequested;
    public event RoutedEventHandler? DownloadPiLogRequested;
    public event RoutedEventHandler? BrowseSasLogFolderRequested;
    public event RoutedEventHandler? BrowsePiLogFolderRequested;

    public LogsView()
    {
        InitializeComponent();
    }

    public string SasLogPath
    {
        get => SasLogPathTextBlock.Text;
        set => SasLogPathTextBlock.Text = value;
    }

    public string SasDestinationFolder
    {
        get => SasLogDestinationTextBox.Text.Trim();
        set => SasLogDestinationTextBox.Text = value;
    }

    public string PiDestinationFolder
    {
        get => PiLogDestinationTextBox.Text.Trim();
        set => PiLogDestinationTextBox.Text = value;
    }

    public string PiLogPreview
    {
        get => PiLogPreviewTextBox.Text;
        set => PiLogPreviewTextBox.Text = value;
    }

    public string PiLogStatus
    {
        get => PiLogStatusTextBlock.Text;
        set => PiLogStatusTextBlock.Text = value;
    }

    public void SetSasLogItemsSource(IEnumerable items)
    {
        LogsListView.ItemsSource = items;
    }

    public void ShowMessage(string title, string message, InfoBarSeverity severity)
    {
        LogsInfoBar.Title = title;
        LogsInfoBar.Message = message;
        LogsInfoBar.Severity = severity;
        LogsInfoBar.IsOpen = true;
    }

    public void SetOperationState(bool busy, string message = "")
    {
        LogsProgressBar.Visibility = busy ? Visibility.Visible : Visibility.Collapsed;
        if (busy && !string.IsNullOrWhiteSpace(message))
        {
            ShowMessage("Please wait", message, InfoBarSeverity.Informational);
        }
    }

    private void DownloadSasLogButton_Click(object sender, RoutedEventArgs e)
    {
        DownloadSasLogRequested?.Invoke(sender, e);
    }

    private void RefreshPiLogsButton_Click(object sender, RoutedEventArgs e)
    {
        RefreshPiLogsRequested?.Invoke(sender, e);
    }

    private void DownloadPiLogButton_Click(object sender, RoutedEventArgs e)
    {
        DownloadPiLogRequested?.Invoke(sender, e);
    }

    private void BrowseSasLogFolderButton_Click(object sender, RoutedEventArgs e)
    {
        BrowseSasLogFolderRequested?.Invoke(sender, e);
    }

    private void BrowsePiLogFolderButton_Click(object sender, RoutedEventArgs e)
    {
        BrowsePiLogFolderRequested?.Invoke(sender, e);
    }
}
