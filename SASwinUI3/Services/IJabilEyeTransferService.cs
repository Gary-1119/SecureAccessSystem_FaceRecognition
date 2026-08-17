using SAS.Models;

namespace SAS.Services;

public interface IJabilEyeTransferService
{
    Task MountServerAsync(AppSettings settings, bool save, CancellationToken cancellationToken = default);
    Task SetCameraRotationAsync(int cameraRotation, CancellationToken cancellationToken = default);
    Task<string> ExportFaceDataToServerAsync(AppSettings settings, string? serverFolder = null, CancellationToken cancellationToken = default);
    Task<string> ExportFaceDataToLocalAsync(string localFolder, CancellationToken cancellationToken = default);
    Task<int> ImportFaceDataFromServerAsync(string zipPath, CancellationToken cancellationToken = default);
    Task<int> ImportFaceDataFromLocalAsync(string localZipPath, CancellationToken cancellationToken = default);
}
