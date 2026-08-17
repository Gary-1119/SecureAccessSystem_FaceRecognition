using SAS.Models;

namespace SAS.Services;

public interface IRecognitionService : IDisposable
{
    event EventHandler<RecognitionStatus>? StatusChanged;
    event EventHandler<RecognitionUnlockEvent>? UnlockRecognized;
    event EventHandler<PreviewFrame>? PreviewFrameAvailable;

    RecognitionStatus CurrentStatus { get; }
    IReadOnlyList<FaceUserRecord> Users { get; }

    Task ConfigureAsync(AppSettings settings, CancellationToken cancellationToken = default);
    Task StartAsync(CancellationToken cancellationToken = default);
    Task StopAsync(CancellationToken cancellationToken = default);
    Task<FaceUserRecord> RegisterCurrentFaceAsync(string displayName, string employeeId, CancellationToken cancellationToken = default);
    Task<bool> DeleteUserAsync(string employeeId, CancellationToken cancellationToken = default);
    Task<string> ExportFaceDataAsync(string folder, CancellationToken cancellationToken = default);
    Task<int> ImportFaceDataAsync(string zipPath, CancellationToken cancellationToken = default);
    Task<int> RestoreLatestImportBackupAsync(CancellationToken cancellationToken = default);
    void ResetUnlockCooldown();
    void EndUnlockSession(string reason = "unlocked");
    void SimulateAuthorizedFace(string name = "Authorized User", string employeeId = "LOCAL");
}
