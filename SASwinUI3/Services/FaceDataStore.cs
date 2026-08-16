using System.IO.Compression;
using System.Text.Json;
using SAS.Models;

namespace SAS.Services;

internal sealed class FaceDataStore
{
    private const string ExportZipPrefix = "SAS_FACE_DATA";
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web) { WriteIndented = true };

    private readonly AppLogService _log;
    private readonly string _dataRoot;
    private readonly string _photosRoot;
    private readonly string _usersPath;

    private List<FaceUserRecord> _users = [];

    public FaceDataStore(AppLogService log)
    {
        _log = log;
        _dataRoot = Path.Combine(AppDataPaths.RootDirectory, "face_data");
        _photosRoot = Path.Combine(_dataRoot, "photos");
        _usersPath = Path.Combine(_dataRoot, "users.json");
        Directory.CreateDirectory(_photosRoot);
        Load();
    }

    public IReadOnlyList<FaceUserRecord> Users => _users.Select(CloneUser).ToList();

    public List<FaceUserRecord> UsersWithEmbeddings()
    {
        return _users.Select(CloneUser).Where(u => u.Embeddings.Count > 0).ToList();
    }

    public void Reload()
    {
        Load();
    }

    public FaceUserRecord AddSample(string displayName, string employeeId, float[] embedding, byte[] jpeg)
    {
        displayName = (displayName ?? "").Trim();
        employeeId = (employeeId ?? "").Trim().ToUpperInvariant();

        var folder = Path.Combine(_photosRoot, employeeId);
        Directory.CreateDirectory(folder);
        var photoPath = Path.Combine(folder, $"{DateTime.Now:yyyyMMdd_HHmmss}.jpg");
        File.WriteAllBytes(photoPath, jpeg);

        var user = _users.FirstOrDefault(u => string.Equals(u.EmployeeId, employeeId, StringComparison.OrdinalIgnoreCase))
            ?? new FaceUserRecord { UserId = employeeId, EmployeeId = employeeId, DisplayName = displayName, CreatedAt = DateTimeOffset.Now };
        user.DisplayName = displayName;
        user.Embeddings.Add(embedding);
        user.SampleCount = user.Embeddings.Count;
        if (!_users.Contains(user))
        {
            _users.Add(user);
        }

        _users = _users.OrderBy(u => u.EmployeeId).ToList();
        Save();
        return CloneUser(user);
    }

    public bool Delete(string employeeId)
    {
        employeeId = (employeeId ?? "").Trim().ToUpperInvariant();
        var removed = _users.RemoveAll(u => string.Equals(u.EmployeeId, employeeId, StringComparison.OrdinalIgnoreCase)) > 0;
        Save();

        var folder = Path.Combine(_photosRoot, employeeId);
        if (Directory.Exists(folder))
        {
            Directory.Delete(folder, recursive: true);
        }

        return removed;
    }

    public string ExportToLocal(string localFolder)
    {
        localFolder = (localFolder ?? "").Trim();
        if (string.IsNullOrWhiteSpace(localFolder))
        {
            throw new InvalidOperationException("Choose an export folder.");
        }

        Directory.CreateDirectory(localFolder);
        Save();

        var zipPath = Path.Combine(localFolder, $"{ExportZipPrefix}_{DateTime.Now:yyyyMMdd_HHmmss}.zip");
        if (File.Exists(zipPath))
        {
            File.Delete(zipPath);
        }

        ZipFile.CreateFromDirectory(_dataRoot, zipPath, CompressionLevel.Optimal, includeBaseDirectory: false);
        return zipPath;
    }

    public int ImportFromLocal(string localZipPath)
    {
        if (!File.Exists(localZipPath))
        {
            throw new FileNotFoundException("Import ZIP was not found.", localZipPath);
        }

        var temp = Path.Combine(Path.GetTempPath(), "SAS_FACE_IMPORT_" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(temp);
        try
        {
            ZipFile.ExtractToDirectory(localZipPath, temp);
            var importedUsersPath = Path.Combine(temp, "users.json");
            if (!File.Exists(importedUsersPath))
            {
                throw new InvalidOperationException("users.json was not found in the selected face-data ZIP.");
            }

            var incoming = JsonSerializer.Deserialize<List<FaceUserRecord>>(File.ReadAllText(importedUsersPath), JsonOptions) ?? [];
            var added = 0;
            foreach (var user in incoming.Where(u => !string.IsNullOrWhiteSpace(u.EmployeeId)))
            {
                user.EmployeeId = user.EmployeeId.Trim().ToUpperInvariant();
                user.DisplayName = string.IsNullOrWhiteSpace(user.DisplayName) ? user.EmployeeId : user.DisplayName.Trim();
                user.SampleCount = user.Embeddings.Count;
                var existing = _users.FirstOrDefault(u => string.Equals(u.EmployeeId, user.EmployeeId, StringComparison.OrdinalIgnoreCase));
                if (existing is null)
                {
                    _users.Add(user);
                    added++;
                }
                else
                {
                    existing.DisplayName = user.DisplayName;
                    existing.Embeddings = user.Embeddings;
                    existing.SampleCount = existing.Embeddings.Count;
                }
            }

            _users = _users.OrderBy(u => u.EmployeeId).ToList();
            Save();
            CopyDirectory(Path.Combine(temp, "photos"), _photosRoot);
            return added;
        }
        finally
        {
            try
            {
                Directory.Delete(temp, recursive: true);
            }
            catch
            {
            }
        }
    }

    private void Load()
    {
        if (!File.Exists(_usersPath))
        {
            _users = [];
            return;
        }

        try
        {
            _users = (JsonSerializer.Deserialize<List<FaceUserRecord>>(File.ReadAllText(_usersPath), JsonOptions) ?? [])
                .Where(u => !string.IsNullOrWhiteSpace(u.EmployeeId))
                .Select(u =>
                {
                    u.EmployeeId = u.EmployeeId.Trim().ToUpperInvariant();
                    u.DisplayName = string.IsNullOrWhiteSpace(u.DisplayName) ? u.EmployeeId : u.DisplayName.Trim();
                    u.SampleCount = u.Embeddings.Count;
                    return u;
                })
                .OrderBy(u => u.EmployeeId)
                .ToList();
        }
        catch (Exception ex)
        {
            _users = [];
            _log.Write($"Local face data load failed: {ex.Message}");
        }
    }

    private void Save()
    {
        Directory.CreateDirectory(_dataRoot);
        File.WriteAllText(_usersPath, JsonSerializer.Serialize(_users, JsonOptions));
    }

    private static FaceUserRecord CloneUser(FaceUserRecord user)
    {
        return new FaceUserRecord
        {
            UserId = user.UserId,
            DisplayName = user.DisplayName,
            EmployeeId = user.EmployeeId,
            CreatedAt = user.CreatedAt,
            SampleCount = user.SampleCount,
            Embeddings = user.Embeddings.Select(e => e.ToArray()).ToList()
        };
    }

    private static void CopyDirectory(string source, string destination)
    {
        if (!Directory.Exists(source))
        {
            return;
        }

        Directory.CreateDirectory(destination);
        foreach (var file in Directory.EnumerateFiles(source, "*", SearchOption.AllDirectories))
        {
            var relative = Path.GetRelativePath(source, file);
            var target = Path.Combine(destination, relative);
            Directory.CreateDirectory(Path.GetDirectoryName(target)!);
            File.Copy(file, target, overwrite: true);
        }
    }
}
