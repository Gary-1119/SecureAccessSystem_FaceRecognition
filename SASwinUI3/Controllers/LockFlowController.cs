using SAS.Models;
using SAS.Services;

namespace SAS.Controllers;

public sealed class LockFlowController
{
    private readonly RuntimeLockService _runtimeLockService;
    private readonly LockWidgetService _lockWidgetService;
    private readonly IRecognitionService _recognitionService;
    private readonly AppLogService _log;

    public event EventHandler? EmergencyUnlockRequested;

    public LockFlowController(
        RuntimeLockService runtimeLockService,
        LockWidgetService lockWidgetService,
        IRecognitionService recognitionService,
        AppLogService log)
    {
        _runtimeLockService = runtimeLockService;
        _lockWidgetService = lockWidgetService;
        _recognitionService = recognitionService;
        _log = log;
        _runtimeLockService.EmergencyUnlockRequested += (_, _) => EmergencyUnlockRequested?.Invoke(this, EventArgs.Empty);
    }

    public bool IsLocked { get; private set; }

    public void Lock(AppSettings settings, string reason, Func<Task> startRecognitionAsync, Action updateUi)
    {
        IsLocked = true;
        _runtimeLockService.Apply(true, settings);
        _lockWidgetService.Show();
        _ = startRecognitionAsync();
        _log.Write($"System locked. Reason: {reason}.");
        updateUi();
    }

    public void Unlock(AppSettings settings, string reason, Action resetInactivity, Action closeReconnectPrompt, Action updateUi)
    {
        IsLocked = false;
        resetInactivity();
        _runtimeLockService.Apply(false, settings);
        _lockWidgetService.Close();
        _recognitionService.EndUnlockSession(reason);
        closeReconnectPrompt();
        _log.Write($"System unlocked. Method: {reason}.");
        updateUi();
    }

    public void ApplyCurrentSettings(AppSettings settings)
    {
        _runtimeLockService.Apply(IsLocked, settings);
    }

    public void BeginCredentialEntryMode(IntPtr allowedWindowHandle, int left, int top, int right, int bottom)
    {
        _runtimeLockService.BeginCredentialEntryMode(allowedWindowHandle, left, top, right, bottom);
    }

    public void EndCredentialEntryMode(AppSettings settings)
    {
        _runtimeLockService.EndCredentialEntryMode(settings);
    }
}
