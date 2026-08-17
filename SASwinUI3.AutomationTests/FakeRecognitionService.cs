using SAS.Models;
using SAS.Services;

namespace SASwinUI3.AutomationTests;

internal sealed class FakeRecognitionService : IRecognitionService
{
    private RecognitionStatus _status = new(false, false, true, "stopped", "", "", 0, null, null, null, null);

    public bool StartPublishesFrame { get; set; } = true;
    public int StopCount { get; private set; }
    public AppSettings ConfiguredSettings { get; private set; } = new();

    public event EventHandler<RecognitionStatus>? StatusChanged;
    public event EventHandler<RecognitionUnlockEvent>? UnlockRecognized;
    public event EventHandler<PreviewFrame>? PreviewFrameAvailable;

    public RecognitionStatus Status
    {
        get => _status;
        set => _status = value;
    }

    public RecognitionStatus CurrentStatus => _status;
    public IReadOnlyList<FaceUserRecord> Users { get; private set; } = [];

    public Task ConfigureAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        ConfiguredSettings = settings.Clone();
        _status = new RecognitionStatus(false, false, true, "disconnected", "", settings.ApiBaseUrl, 0, null, null, null, null);
        StatusChanged?.Invoke(this, _status);
        return Task.CompletedTask;
    }

    public Task StartAsync(CancellationToken cancellationToken = default)
    {
        _status = StartPublishesFrame
            ? new RecognitionStatus(true, true, true, "live", "", ConfiguredSettings.ApiBaseUrl, 0, DateTimeOffset.Now, null, null, null)
            : new RecognitionStatus(true, false, true, "disconnected", "Could not connect.", ConfiguredSettings.ApiBaseUrl, 1, null, null, null, null);
        StatusChanged?.Invoke(this, _status);
        if (StartPublishesFrame)
        {
            PreviewFrameAvailable?.Invoke(this, new PreviewFrame([0xFF, 0xD8, 0xFF, 0xD9], DateTimeOffset.Now));
        }

        return Task.CompletedTask;
    }

    public Task StopAsync(CancellationToken cancellationToken = default)
    {
        StopCount++;
        _status = new RecognitionStatus(false, false, true, "sas preview stopped", "", ConfiguredSettings.ApiBaseUrl, 0, null, null, null, null);
        StatusChanged?.Invoke(this, _status);
        return Task.CompletedTask;
    }

    public Task<FaceUserRecord> RegisterCurrentFaceAsync(string displayName, string employeeId, CancellationToken cancellationToken = default)
    {
        var user = new FaceUserRecord { DisplayName = displayName, EmployeeId = employeeId.ToUpperInvariant(), SampleCount = 1 };
        Users = [user];
        return Task.FromResult(user);
    }

    public Task<bool> DeleteUserAsync(string employeeId, CancellationToken cancellationToken = default)
    {
        Users = Users.Where(user => !string.Equals(user.EmployeeId, employeeId, StringComparison.OrdinalIgnoreCase)).ToList();
        return Task.FromResult(true);
    }

    public Task<string> ExportFaceDataAsync(string folder, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(Path.Combine(folder, "face_data.zip"));
    }

    public Task<int> ImportFaceDataAsync(string zipPath, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(1);
    }

    public Task<int> RestoreLatestImportBackupAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult(0);
    }

    public void ResetUnlockCooldown()
    {
    }

    public void EndUnlockSession(string reason = "unlocked")
    {
    }

    public void SimulateAuthorizedFace(string name = "Authorized User", string employeeId = "LOCAL")
    {
        UnlockRecognized?.Invoke(this, new RecognitionUnlockEvent(name, employeeId, 99, Guid.NewGuid().ToString("N"), DateTimeOffset.Now));
    }

    public void Dispose()
    {
    }
}
