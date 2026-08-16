using SAS.Models;
using SAS.Services;

namespace SAS.Controllers;

public sealed class SettingsController
{
    private readonly AppSettingsService _settingsService;
    private readonly UserAuthService _authService;
    private readonly IRecognitionService _recognitionService;
    private readonly IJabilEyeTransferService? _jabilEyeTransferService;
    private readonly LockFlowController _lockFlowController;
    private readonly AppLogService _log;

    public SettingsController(
        AppSettingsService settingsService,
        UserAuthService authService,
        IRecognitionService recognitionService,
        IJabilEyeTransferService? jabilEyeTransferService,
        LockFlowController lockFlowController,
        AppLogService log)
    {
        _settingsService = settingsService;
        _authService = authService;
        _recognitionService = recognitionService;
        _jabilEyeTransferService = jabilEyeTransferService;
        _lockFlowController = lockFlowController;
        _log = log;
    }

    public IReadOnlyList<string> AdminNtids => _authService.Admins.Select(user => user.Ntid).ToList();

    public AppUser AddAdmin(string ntid)
    {
        _authService.ValidateNtidExists(ntid);
        var admin = _authService.AddAdmin(ntid);
        _log.Write($"Admin added: {admin.Ntid}.");
        _log.WriteAudit("ADMIN ADDED", admin.Ntid);
        return admin;
    }

    public void RemoveAdmin(string ntid)
    {
        _authService.RemoveAdmin(ntid);
        _log.Write($"Admin removed: {ntid}.");
        _log.WriteAudit("ADMIN REMOVED", ntid);
    }

    public async Task SaveSettingsAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        _settingsService.Save(settings);
        await _recognitionService.ConfigureAsync(settings, cancellationToken);
        if (_jabilEyeTransferService is not null)
        {
            await PushCameraRotationToPiAsync(settings, cancellationToken);
            await TryMountConfiguredServerAsync(settings, cancellationToken);
        }

        _lockFlowController.ApplyCurrentSettings(settings);
        _log.Write("Settings saved.");
        _log.WriteAudit("SETTINGS CHANGED", BuildSettingsAuditDetails(settings));
    }

    public async Task MountServerAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        if (_jabilEyeTransferService is null)
        {
            return;
        }

        _settingsService.Save(settings);
        if (string.IsNullOrWhiteSpace(settings.ServerPath) ||
            string.IsNullOrWhiteSpace(settings.ServerUsername) ||
            string.IsNullOrWhiteSpace(settings.ServerPassword))
        {
            _log.ConfigureServerLogPath(settings.ServerPath);
            _log.Write("Server mount settings saved; server path or credentials are blank.");
            _log.WriteAudit("SERVER MOUNT SAVED", $"ServerPath={settings.ServerPath}; Owner={settings.ServerCredentialOwnerNtid}");
            return;
        }

        await _jabilEyeTransferService.MountServerAsync(settings, save: true, cancellationToken);
        var serverLogDirectory = _log.ConfigureServerLogPath(settings.ServerPath);
        _log.Write($"Server log path saved: {serverLogDirectory}");
        _log.WriteAudit("SERVER LOG PATH CHANGED", $"ServerPath={settings.ServerPath}; LogDirectory={serverLogDirectory}; Owner={settings.ServerCredentialOwnerNtid}");
    }

    public async Task PushCameraRotationToPiAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        if (_jabilEyeTransferService is null)
        {
            return;
        }

        try
        {
            await _jabilEyeTransferService.SetCameraRotationAsync(settings.CameraRotation, cancellationToken);
            _log.Write($"Camera rotation set to {settings.CameraRotation}.");
        }
        catch (Exception ex)
        {
            _log.Write($"Camera rotation save warning: {ex.Message}");
        }
    }

    private async Task TryMountConfiguredServerAsync(AppSettings settings, CancellationToken cancellationToken)
    {
        if (_jabilEyeTransferService is null || string.IsNullOrWhiteSpace(settings.ServerPath))
        {
            return;
        }

        try
        {
            await _jabilEyeTransferService.MountServerAsync(settings, save: true, cancellationToken);
            _log.ConfigureServerLogPath(settings.ServerPath);
        }
        catch (Exception ex)
        {
            _log.Write($"Server mount/save warning: {ex.Message}");
        }
    }

    private static string BuildSettingsAuditDetails(AppSettings settings)
    {
        return $"CameraHost={settings.JabilEyeHost}; RtspPort={settings.RtspPort}; RtspPath={settings.RtspPath}; Rotation={settings.CameraRotation}; LockTimeoutSeconds={settings.LockTimeoutSeconds}; DisableKeyboard={settings.DisableKeyboardWhenLocked}; DisableMouse={settings.DisableMouseWhenLocked}; DisableUsb={settings.DisableUsbWhenLocked}; EmergencyHotkey={settings.EnableEmergencyHotkey}; ServerPath={settings.ServerPath}";
    }
}
