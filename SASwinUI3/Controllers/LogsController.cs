using SAS.Services;

namespace SAS.Controllers;

public sealed class LogsController
{
    private readonly AppLogService _log;

    public LogsController(AppLogService log)
    {
        _log = log;
    }

    public async Task<string> DownloadSasLogAsync(string destinationFolder, CancellationToken cancellationToken = default)
    {
        var folder = EnsureDestinationFolder(destinationFolder);
        _log.WriteAudit("SAS LOG DOWNLOADED", $"DestinationFolder={folder}");
        return await _log.ExportTodayLogAsync(folder, cancellationToken);
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

}
