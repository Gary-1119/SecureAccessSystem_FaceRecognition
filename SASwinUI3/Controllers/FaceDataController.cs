using System.IO.Compression;
using SAS.Models;
using SAS.Services;

namespace SAS.Controllers;

public sealed class FaceDataController
{
    private readonly IJabilEyeTransferService _transferService;
    private readonly AppLogService _log;

    public FaceDataController(IJabilEyeTransferService transferService, AppLogService log)
    {
        _transferService = transferService;
        _log = log;
    }

    public async Task<string> ExportAsync(FaceDataExportRequest request, CancellationToken cancellationToken = default)
    {
        if (!request.ExportLocal && request.ServerSettings is null)
        {
            throw new InvalidOperationException("Enter the NTID, Password, and export path for this export.");
        }

        var path = request.ExportLocal
            ? await _transferService.ExportFaceDataToLocalAsync(request.ExportPath, cancellationToken)
            : await _transferService.ExportFaceDataToServerAsync(request.ServerSettings!, request.ExportPath, cancellationToken);

        _log.Write($"Export complete: {path}");
        _log.WriteAudit("FACE DATA EXPORTED", $"Mode={(request.ExportLocal ? "Local" : "SMB")}; Path={path}");
        return path;
    }

    public async Task<int> ImportAsync(FaceDataImportRequest request, CancellationToken cancellationToken = default)
    {
        if (!IsZipPath(request.ImportZipPath))
        {
            throw new FaceDataValidationException("ZIP file required", "Choose a .zip file for face-data import.");
        }

        if (!request.ImportLocal)
        {
            if (IsWindowsDrivePath(request.ImportZipPath))
            {
                throw new FaceDataValidationException("Use Local ZIP", "This is a local Windows path. Change Import from to Local ZIP, or choose a ZIP from a UNC SMB path like //server/share/folder/file.zip.");
            }

            if (request.ServerSettings is null)
            {
                throw new FaceDataValidationException("Credentials required", "Enter the NTID, Password, and ZIP path for this import.");
            }

            await _transferService.MountServerAsync(request.ServerSettings, save: false, cancellationToken);
        }

        var added = request.ImportLocal
            ? await _transferService.ImportFaceDataFromLocalAsync(request.ImportZipPath, cancellationToken)
            : await _transferService.ImportFaceDataFromServerAsync(request.ImportZipPath, cancellationToken);

        _log.Write($"Import complete: {added} new users.");
        _log.WriteAudit("FACE DATA IMPORTED", $"Mode={(request.ImportLocal ? "Local" : "SMB")}; Source={request.ImportZipPath}; Added={added}");
        return added;
    }

    public static AppSettings? CreateTemporaryServerSettings(AppSettings currentSettings, string usernameValue, string passwordValue, string pathValue)
    {
        var username = usernameValue.Trim();
        var password = passwordValue;
        var serverPath = NormalizeServerPath(pathValue);
        if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password) || string.IsNullOrWhiteSpace(serverPath))
        {
            return null;
        }

        return new AppSettings
        {
            CameraHost = currentSettings.CameraHost,
            ApiPort = currentSettings.ApiPort,
            ClientId = currentSettings.ClientId,
            ClientName = currentSettings.ClientName,
            ServerUsername = username,
            ServerPassword = password,
            ServerPath = serverPath,
            CameraSource = currentSettings.CameraSource,
            CameraRotation = currentSettings.CameraRotation,
            LockTimeoutSeconds = currentSettings.LockTimeoutSeconds,
            DisableKeyboardWhenLocked = currentSettings.DisableKeyboardWhenLocked,
            DisableMouseWhenLocked = currentSettings.DisableMouseWhenLocked,
            DisableUsbWhenLocked = currentSettings.DisableUsbWhenLocked,
            EnableEmergencyHotkey = currentSettings.EnableEmergencyHotkey
        };
    }

    public static string GetServerMountPathFromImportPath(string importPath)
    {
        var value = NormalizeServerPath(importPath);
        if (!value.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
        {
            return value;
        }

        var lastSlash = Math.Max(value.LastIndexOf('/'), value.LastIndexOf('\\'));
        return lastSlash > 0 ? value[..lastSlash] : value;
    }

    public static string NormalizeServerPath(string path)
    {
        var value = (path ?? "").Trim().Replace('\\', '/');
        while (value.StartsWith("////", StringComparison.Ordinal))
        {
            value = value[1..];
        }

        return value;
    }

    public static string BuildImportErrorMessage(Exception exception)
    {
        return exception switch
        {
            FaceDataValidationException ex => ex.Message,
            FileNotFoundException => "The selected ZIP file was not found. Choose an exported SAS face-data ZIP and try again.",
            InvalidDataException => "The selected file is not a valid ZIP file. Choose an exported SAS face-data ZIP.",
            InvalidOperationException ex when ex.Message.Contains("users.json", StringComparison.OrdinalIgnoreCase) => "This ZIP is not a SAS face-data export. It must contain users.json, embeddings.bin, embedding_index.json, and photos at the ZIP root.",
            _ => exception.Message
        };
    }

    private static bool IsZipPath(string path)
    {
        return !string.IsNullOrWhiteSpace(path) &&
            path.EndsWith(".zip", StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsWindowsDrivePath(string path)
    {
        return path.Length >= 3 &&
            char.IsLetter(path[0]) &&
            path[1] == ':' &&
            path[2] == '/';
    }
}

public sealed record FaceDataExportRequest(bool ExportLocal, string ExportPath, AppSettings? ServerSettings);

public sealed record FaceDataImportRequest(bool ImportLocal, string ImportZipPath, AppSettings? ServerSettings);

public sealed class FaceDataValidationException : InvalidOperationException
{
    public FaceDataValidationException(string title, string message) : base(message)
    {
        Title = title;
    }

    public string Title { get; }
}
