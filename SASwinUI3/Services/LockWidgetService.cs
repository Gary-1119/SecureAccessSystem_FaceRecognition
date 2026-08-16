namespace SAS.Services;

public sealed class LockWidgetService
{
    private readonly Action _showWidget;
    private readonly Action _closeWidget;
    private readonly AppLogService _log;

    public LockWidgetService(Action showWidget, Action closeWidget, AppLogService log)
    {
        _showWidget = showWidget;
        _closeWidget = closeWidget;
        _log = log;
    }

    public void Show()
    {
        try
        {
            _showWidget();
            _log.Write("Lock widget opened.");
        }
        catch (Exception ex)
        {
            _log.Write($"Lock widget failed to open: {ex.Message}");
        }
    }

    public void Close()
    {
        _closeWidget();
        _log.Write("Lock widget closed.");
    }
}
