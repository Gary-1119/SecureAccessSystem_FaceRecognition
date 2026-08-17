using System.IO.Compression;
using System.Text.Json.Nodes;
using SAS.Models;

namespace SAS.Services;

public sealed class PiFaceDataApi
{
    private readonly PiApiClient _api;
    private readonly PiSftpFileTransferService _sftpFileTransfer;
    private readonly Func<CancellationToken, Task<(string Username, string Password)>> _getSftpCredentialsAsync;
    private readonly Func<CancellationToken, Task> _refreshUsersAsync;
    private readonly Func<string> _getPiHost;

    public PiFaceDataApi(
        PiApiClient api,
        PiSftpFileTransferService sftpFileTransfer,
        Func<CancellationToken, Task<(string Username, string Password)>> getSftpCredentialsAsync,
        Func<CancellationToken, Task> refreshUsersAsync,
        Func<string> getPiHost)
    {
        _api = api;
        _sftpFileTransfer = sftpFileTransfer;
        _getSftpCredentialsAsync = getSftpCredentialsAsync;
        _refreshUsersAsync = refreshUsersAsync;
        _getPiHost = getPiHost;
    }

    public async Task MountServerAsync(AppSettings settings, bool save, CancellationToken cancellationToken = default)
    {
        await _api.RequestAsync("POST", "/server/mount", new JsonObject
        {
            ["username"] = settings.ServerUsername,
            ["password"] = settings.ServerPassword,
            ["pc_save_path"] = settings.ServerPath,
            ["save"] = save
        }, timeoutSeconds: 60, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async Task SetCameraRotationAsync(int cameraRotation, CancellationToken cancellationToken = default)
    {
        await _api.RequestAsync("POST", "/settings", new JsonObject
        {
            ["camera_rotation"] = cameraRotation,
            ["source"] = "Windows SAS"
        }, timeoutSeconds: 15, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async Task<string> ExportFaceDataToServerAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        var data = await _api.RequestAsync("POST", "/face-data/export", new JsonObject
        {
            ["username"] = settings.ServerUsername,
            ["password"] = settings.ServerPassword,
            ["pc_save_path"] = settings.ServerPath
        }, timeoutSeconds: 300, cancellationToken: cancellationToken).ConfigureAwait(false);
        return PiJson.ReadString(data, "zip_path", "file", "path", "filename", "message");
    }

    public async Task<string> ExportFaceDataToLocalAsync(string localFolder, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(localFolder))
        {
            throw new InvalidOperationException("Choose a local export folder.");
        }

        Directory.CreateDirectory(localFolder);
        var prepare = await _api.RequestAsync("POST", "/face-data/sftp-prepare-download", timeoutSeconds: 120, cancellationToken: cancellationToken).ConfigureAwait(false);
        var remotePath = PiJson.ReadString(prepare, "remote_path", "zip_path");
        var filename = PiJson.ReadString(prepare, "filename");
        if (string.IsNullOrWhiteSpace(remotePath))
        {
            throw new InvalidOperationException("Pi did not return a downloadable ZIP path.");
        }

        filename = string.IsNullOrWhiteSpace(filename) ? Path.GetFileName(remotePath) : filename;
        var localPath = Path.Combine(localFolder, filename);
        var (username, password) = await _getSftpCredentialsAsync(cancellationToken).ConfigureAwait(false);
        await _sftpFileTransfer.DownloadAsync(_getPiHost(), username, password, remotePath, localPath, cancellationToken).ConfigureAwait(false);
        return localPath;
    }

    public async Task<int> ImportFaceDataFromServerAsync(string zipPath, CancellationToken cancellationToken = default)
    {
        var data = await _api.RequestAsync("POST", "/face-data/import", new JsonObject { ["zip_path"] = zipPath }, timeoutSeconds: 180, cancellationToken: cancellationToken).ConfigureAwait(false);
        await _refreshUsersAsync(cancellationToken).ConfigureAwait(false);
        return ReadImportedCount(data);
    }

    public async Task<int> ImportFaceDataFromLocalAsync(string localZipPath, CancellationToken cancellationToken = default)
    {
        if (!File.Exists(localZipPath))
        {
            throw new FileNotFoundException("Import ZIP was not found.", localZipPath);
        }

        var target = await _api.RequestAsync("POST", "/face-data/sftp-import-target", timeoutSeconds: 60, cancellationToken: cancellationToken).ConfigureAwait(false);
        var remoteDir = PiJson.ReadString(target, "remote_dir", "import_dir");
        if (string.IsNullOrWhiteSpace(remoteDir))
        {
            throw new InvalidOperationException("Pi did not return an import target folder.");
        }

        var remotePath = PiSftpFileTransferService.CombineUnixPath(remoteDir, Path.GetFileName(localZipPath));
        var (username, password) = await _getSftpCredentialsAsync(cancellationToken).ConfigureAwait(false);
        await _sftpFileTransfer.UploadAsync(_getPiHost(), username, password, localZipPath, remotePath, cancellationToken).ConfigureAwait(false);
        return await ImportFaceDataFromServerAsync(remotePath, cancellationToken).ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<string>> ListSftpTargetsAsync(CancellationToken cancellationToken = default)
    {
        var data = await _api.RequestAsync("GET", "/face-data/sftp-targets", timeoutSeconds: 15, cancellationToken: cancellationToken).ConfigureAwait(false);
        return PiJson.ReadStringList(data, "targets", "hosts", "items");
    }

    public async Task AddSftpTargetAsync(string hostname, bool requireReachable = true, CancellationToken cancellationToken = default)
    {
        if (requireReachable)
        {
            await PiSftpFileTransferService.EnsureReachableAsync(hostname, cancellationToken).ConfigureAwait(false);
        }

        await _api.RequestAsync("POST", "/face-data/sftp-targets", new JsonObject { ["hostname"] = hostname }, timeoutSeconds: 15, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async Task RemoveSftpTargetAsync(string hostname, CancellationToken cancellationToken = default)
    {
        await _api.RequestAsync("DELETE", $"/face-data/sftp-targets/{Uri.EscapeDataString(hostname)}", timeoutSeconds: 15, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async Task<string> StartMultiSftpTransferAsync(IEnumerable<string> targets, CancellationToken cancellationToken = default)
    {
        var array = new JsonArray();
        foreach (var target in targets.Where(t => !string.IsNullOrWhiteSpace(t)))
        {
            array.Add(target.Trim());
        }

        var data = await _api.RequestAsync("POST", "/face-data/sftp-multi-send", new JsonObject { ["targets"] = array }, timeoutSeconds: 30, cancellationToken: cancellationToken).ConfigureAwait(false);
        if (data["batch"] is JsonObject batch)
        {
            var nestedId = PiJson.ReadString(batch, "batch_id", "id");
            if (!string.IsNullOrWhiteSpace(nestedId))
            {
                return nestedId;
            }
        }

        return PiJson.ReadString(data, "batch_id", "id", "message");
    }

    public Task<JsonObject> GetMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default)
    {
        return _api.RequestAsync("GET", $"/face-data/sftp-multi-send/{Uri.EscapeDataString(batchId)}", timeoutSeconds: 15, cancellationToken: cancellationToken);
    }

    public Task<JsonObject> CancelMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default)
    {
        return _api.RequestAsync("POST", $"/face-data/sftp-multi-send/{Uri.EscapeDataString(batchId)}/cancel", timeoutSeconds: 20, cancellationToken: cancellationToken);
    }

    public async Task<IReadOnlyList<string>> ListReceivedAsync(CancellationToken cancellationToken = default)
    {
        var data = await _api.RequestAsync("GET", "/face-data/received", timeoutSeconds: 20, cancellationToken: cancellationToken).ConfigureAwait(false);
        return PiJson.ReadStringList(data, "pending", "files", "items");
    }

    public async Task<int> AcceptReceivedAsync(string filename, CancellationToken cancellationToken = default)
    {
        var data = await _api.RequestAsync("POST", "/face-data/received/accept", new JsonObject { ["filename"] = filename }, timeoutSeconds: 120, cancellationToken: cancellationToken).ConfigureAwait(false);
        await _refreshUsersAsync(cancellationToken).ConfigureAwait(false);
        return ReadImportedCount(data);
    }

    public async Task RejectReceivedAsync(string filename, CancellationToken cancellationToken = default)
    {
        await _api.RequestAsync("POST", "/face-data/received/reject", new JsonObject { ["filename"] = filename }, timeoutSeconds: 45, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    public async Task<PiStorageInfo> GetStorageInfoAsync(CancellationToken cancellationToken = default)
    {
        Exception? lastError = null;
        foreach (var endpoint in new[] { "/storage", "/system/storage", "/face-data/storage", "/disk" })
        {
            try
            {
                var data = await _api.RequestAsync("GET", endpoint, timeoutSeconds: 10, cancellationToken: cancellationToken).ConfigureAwait(false);
                return ParseStorageInfo(data);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                lastError = ex;
            }
        }

        throw new InvalidOperationException(lastError?.Message ?? "Pi storage API is unavailable.");
    }

    public async Task<IReadOnlyList<string>> GetPiLogsAsync(CancellationToken cancellationToken = default)
    {
        var data = await _api.RequestAsync("GET", "/logs", timeoutSeconds: 20, cancellationToken: cancellationToken).ConfigureAwait(false);
        return PiJson.ReadStringList(data, "logs", "lines", "items");
    }

    public async Task ClearPiLogsAsync(CancellationToken cancellationToken = default)
    {
        await _api.RequestAsync("POST", "/logs/clear", timeoutSeconds: 20, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private static int ReadImportedCount(JsonObject data)
    {
        return PiJson.ReadInt(data, "imported", "added", "count", "users");
    }

    private static PiStorageInfo ParseStorageInfo(JsonObject data)
    {
        if (data["storage"] is JsonObject storage)
        {
            data = storage;
        }
        else if (data["disk"] is JsonObject disk)
        {
            data = disk;
        }

        var total = PiJson.ReadLong(data, "total_bytes", "total", "size", "capacity");
        var free = PiJson.ReadLong(data, "free_bytes", "free", "available", "available_bytes");
        var used = PiJson.ReadLong(data, "used_bytes", "used");
        var usedPercent = PiJson.ReadDouble(data, "used_percent", "percent_used", "usage_percent", "percent");

        if (total > 0 && free == 0 && used > 0)
        {
            free = Math.Max(0, total - used);
        }

        if (total > 0 && used == 0 && free >= 0)
        {
            used = Math.Max(0, total - free);
        }

        if (usedPercent <= 0 && total > 0)
        {
            usedPercent = used * 100d / total;
        }

        var label = PiJson.ReadString(data, "label", "message", "path", "mount");
        if (string.IsNullOrWhiteSpace(label))
        {
            label = total > 0
                ? $"{FormatBytes(free)} free of {FormatBytes(total)}"
                : "Storage available";
        }

        return new PiStorageInfo(total, free, used, Math.Clamp(usedPercent, 0, 100), label);
    }

    private static string FormatBytes(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        var value = Math.Max(0, bytes);
        var size = (double)value;
        var unit = 0;
        while (size >= 1024 && unit < units.Length - 1)
        {
            size /= 1024;
            unit++;
        }

        return $"{size:0.#} {units[unit]}";
    }
}
