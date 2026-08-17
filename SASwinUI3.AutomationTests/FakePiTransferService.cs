using System.Text.Json.Nodes;
using SAS.Models;
using SAS.Services;

namespace SASwinUI3.AutomationTests;

internal sealed class FakePiTransferService : IPiTransferService
{
    public bool ImportLocalCalled { get; private set; }
    public IReadOnlyList<string> PiLogs { get; set; } = [];

    public Task MountServerAsync(AppSettings settings, bool save, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }

    public Task SetCameraRotationAsync(int cameraRotation, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }

    public Task<string> ExportFaceDataToServerAsync(AppSettings settings, string? serverFolder = null, CancellationToken cancellationToken = default)
    {
        return Task.FromResult($"{settings.ServerPath}/face_data.zip");
    }

    public Task<string> ExportFaceDataToLocalAsync(string localFolder, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(Path.Combine(localFolder, "face_data.zip"));
    }

    public Task<int> ImportFaceDataFromServerAsync(string zipPath, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(1);
    }

    public Task<int> ImportFaceDataFromLocalAsync(string localZipPath, CancellationToken cancellationToken = default)
    {
        ImportLocalCalled = true;
        return Task.FromResult(1);
    }

    public Task<IReadOnlyList<string>> ListSftpTargetsAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult<IReadOnlyList<string>>(["PI-01", "PI-02"]);
    }

    public Task AddSftpTargetAsync(string hostname, bool requireReachable = true, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }

    public Task RemoveSftpTargetAsync(string hostname, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }

    public Task<string> StartMultiSftpTransferAsync(IEnumerable<string> targets, CancellationToken cancellationToken = default)
    {
        return Task.FromResult("batch-1");
    }

    public Task<JsonObject> GetMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(new JsonObject { ["id"] = batchId, ["state"] = "complete" });
    }

    public Task<JsonObject> CancelMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(new JsonObject { ["id"] = batchId, ["state"] = "cancelled" });
    }

    public Task<IReadOnlyList<string>> ListReceivedAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult<IReadOnlyList<string>>(["pending.zip"]);
    }

    public Task<int> AcceptReceivedAsync(string filename, CancellationToken cancellationToken = default)
    {
        return Task.FromResult(1);
    }

    public Task RejectReceivedAsync(string filename, CancellationToken cancellationToken = default)
    {
        return Task.CompletedTask;
    }

    public Task<PiStorageInfo> GetStorageInfoAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult(new PiStorageInfo(100, 25, 75, 75, "25 B free of 100 B"));
    }

    public Task<IReadOnlyList<string>> GetPiLogsAsync(CancellationToken cancellationToken = default)
    {
        return Task.FromResult(PiLogs);
    }

    public Task ClearPiLogsAsync(CancellationToken cancellationToken = default)
    {
        PiLogs = [];
        return Task.CompletedTask;
    }
}
