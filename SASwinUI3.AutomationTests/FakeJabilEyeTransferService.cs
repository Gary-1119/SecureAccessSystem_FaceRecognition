using SAS.Models;
using SAS.Services;

namespace SASwinUI3.AutomationTests;

internal sealed class FakeJabilEyeTransferService : IJabilEyeTransferService
{
    public bool ImportLocalCalled { get; private set; }

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

}
