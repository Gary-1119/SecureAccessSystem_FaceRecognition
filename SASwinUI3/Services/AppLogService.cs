using System.Collections.ObjectModel;

namespace SAS.Services;

public sealed class AppLogService
{
    private const int RetentionDays = 90;
    private const long LegacyLogMaxBytes = 5 * 1024 * 1024;

    private readonly Action<Action> _enqueueOnUiThread;
    private readonly string _legacyLogPath;
    private readonly object _fileGate = new();
    private string? _serverLogDirectory;

    public ObservableCollection<string> Entries { get; } = [];
    public string LogDirectory { get; }
    public string TodayLogPath => Path.Combine(LogDirectory, $"SAS_LOG_{DateTime.Now:yyyyMMdd}.txt");
    public string? ServerLogDirectory
    {
        get
        {
            lock (_fileGate)
            {
                return _serverLogDirectory;
            }
        }
    }

    public AppLogService(Action<Action> enqueueOnUiThread)
    {
        _enqueueOnUiThread = enqueueOnUiThread;
        var appRoot = AppDataPaths.RootDirectory;
        LogDirectory = Path.Combine(appRoot, "SAS_LOG");
        Directory.CreateDirectory(LogDirectory);
        _legacyLogPath = Path.Combine(appRoot, "app.log");
        CleanupExpiredLogs();
        LoadRecentEntries();
    }

    public void Write(string message)
    {
        WriteAudit("APP", message);
    }

    public string? ConfigureServerLogPath(string serverPath)
    {
        lock (_fileGate)
        {
            if (string.IsNullOrWhiteSpace(serverPath))
            {
                _serverLogDirectory = null;
                return null;
            }

            var logDirectory = Path.Combine(serverPath.Trim(), "SAS_LOG");
            Directory.CreateDirectory(logDirectory);
            _serverLogDirectory = logDirectory;
            return _serverLogDirectory;
        }
    }

    public void WriteAudit(string action, string details = "")
    {
        var actor = GetActor();
        var cleanAction = string.IsNullOrWhiteSpace(action) ? "APP" : action.Trim().ToUpperInvariant();
        var cleanDetails = (details ?? "").Replace(Environment.NewLine, " ").Trim();
        var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} | {actor} | {cleanAction} | {cleanDetails}";
        WriteFileLine(line);
        _enqueueOnUiThread(() => Add(line));
    }

    public async Task<string> ExportTodayLogAsync(string destinationFolder, CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(destinationFolder))
        {
            throw new InvalidOperationException("Choose a local folder for the SAS log.");
        }

        Directory.CreateDirectory(destinationFolder);
        EnsureTodayLogExists();
        var destinationPath = Path.Combine(destinationFolder, Path.GetFileName(TodayLogPath));
        await using var source = File.Open(TodayLogPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        await using var destination = File.Create(destinationPath);
        await source.CopyToAsync(destination, cancellationToken);
        return destinationPath;
    }

    private void WriteFileLine(string line)
    {
        try
        {
            lock (_fileGate)
            {
                File.AppendAllText(TodayLogPath, line + Environment.NewLine);
                File.AppendAllText(_legacyLogPath, line + Environment.NewLine);
                if (!string.IsNullOrWhiteSpace(_serverLogDirectory))
                {
                    var serverLogPath = Path.Combine(_serverLogDirectory, $"SAS_LOG_{DateTime.Now:yyyyMMdd}.txt");
                    File.AppendAllText(serverLogPath, line + Environment.NewLine);
                }
            }
        }
        catch
        {
        }
    }

    private void CleanupExpiredLogs()
    {
        try
        {
            var cutoff = DateTime.Now.Date.AddDays(-RetentionDays);
            foreach (var file in Directory.EnumerateFiles(LogDirectory, "SAS_LOG_*.txt"))
            {
                var fileName = Path.GetFileNameWithoutExtension(file);
                var dateText = fileName.Replace("SAS_LOG_", "", StringComparison.OrdinalIgnoreCase);
                if (DateTime.TryParseExact(dateText, "yyyyMMdd", null, System.Globalization.DateTimeStyles.None, out var logDate) &&
                    logDate.Date < cutoff)
                {
                    File.Delete(file);
                }
            }

            TrimLegacyLogIfNeeded();
        }
        catch
        {
        }
    }

    private void TrimLegacyLogIfNeeded()
    {
        if (!File.Exists(_legacyLogPath) || new FileInfo(_legacyLogPath).Length <= LegacyLogMaxBytes)
        {
            return;
        }

        var tail = File.ReadLines(_legacyLogPath).Reverse().Take(2000).Reverse().ToList();
        File.WriteAllLines(_legacyLogPath, tail);
    }

    private void EnsureTodayLogExists()
    {
        lock (_fileGate)
        {
            if (!File.Exists(TodayLogPath))
            {
                File.WriteAllText(TodayLogPath, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} | {GetActor()} | LOG CREATED | SAS log file initialized.{Environment.NewLine}");
            }
        }
    }

    private void LoadRecentEntries()
    {
        try
        {
            if (!File.Exists(TodayLogPath))
            {
                return;
            }

            foreach (var line in File.ReadLines(TodayLogPath).Reverse().Take(300))
            {
                Entries.Add(line);
            }
        }
        catch
        {
        }
    }

    private void Add(string line)
    {
        Entries.Insert(0, line);
        while (Entries.Count > 300)
        {
            Entries.RemoveAt(Entries.Count - 1);
        }
    }

    private static string GetActor()
    {
        if (AppSession.IsAuthenticated && !string.IsNullOrWhiteSpace(AppSession.Ntid))
        {
            return AppSession.Ntid.ToUpperInvariant();
        }

        return Environment.UserName.ToUpperInvariant();
    }
}
