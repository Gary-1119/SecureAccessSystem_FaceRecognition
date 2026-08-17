using SAS.Models;
using SAS.Services;

namespace SAS.Controllers;

public sealed class LogsController
{
    private readonly AppLogService _log;
    private readonly IPiTransferService? _piTransferService;

    public LogsController(AppLogService log, IPiTransferService? piTransferService)
    {
        _log = log;
        _piTransferService = piTransferService;
    }

    public async Task<string> DownloadSasLogAsync(string destinationFolder, CancellationToken cancellationToken = default)
    {
        var folder = EnsureDestinationFolder(destinationFolder);
        _log.WriteAudit("SAS LOG DOWNLOADED", $"DestinationFolder={folder}");
        return await _log.ExportTodayLogAsync(folder, cancellationToken);
    }

    public async Task<IReadOnlyList<string>> RefreshPiLogsAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        if (_piTransferService is null)
        {
            return [];
        }

        var lines = await _piTransferService.GetPiLogsAsync(cancellationToken);
        _log.WriteAudit("PI LOG VIEWED", $"Lines={lines.Count}; Host={settings.PiHost}");
        return lines;
    }

    public async Task<PiLogDownloadResult> DownloadPiLogAsync(AppSettings settings, string destinationFolder, CancellationToken cancellationToken = default)
    {
        var folder = EnsureDestinationFolder(destinationFolder);
        var lines = await RefreshPiLogsAsync(settings, cancellationToken);
        var fileName = $"PI_LOG_{SanitizeFileName(settings.PiHost)}_{DateTime.Now:yyyyMMdd_HHmmss}.txt";
        var path = Path.Combine(folder, fileName);
        await File.WriteAllLinesAsync(path, lines.Count == 0 ? ["No Pi logs returned."] : lines, cancellationToken);
        _log.WriteAudit("PI LOG DOWNLOADED", $"Host={settings.PiHost}; Destination={path}; Lines={lines.Count}");
        return new PiLogDownloadResult(path, lines);
    }

    public static string EnsureDestinationFolder(string folder)
    {
        folder = (folder ?? "").Trim();
        if (string.IsNullOrWhiteSpace(folder))
        {
            throw new InvalidOperationException("Enter a download folder or press Browse.");
        }

        Directory.CreateDirectory(folder);
        return folder;
    }

    private static string SanitizeFileName(string value)
    {
        var fileName = string.IsNullOrWhiteSpace(value) ? "Pi" : value.Trim();
        foreach (var invalid in Path.GetInvalidFileNameChars())
        {
            fileName = fileName.Replace(invalid, '_');
        }

        return fileName;
    }
}

public sealed record PiLogDownloadResult(string Path, IReadOnlyList<string> Lines);
