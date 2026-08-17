using System.Text.Json;
using SAS.Models;

namespace SAS.Services;

public sealed class AppSettingsService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private readonly string _settingsPath;

    public AppSettingsService()
    {
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var oldRoot = Path.Combine(localAppData, "FaceLockApp");
        var root = Path.Combine(localAppData, "SAS");
        MigrateOldAppData(oldRoot, root);
        Directory.CreateDirectory(root);
        _settingsPath = Path.Combine(root, "settings.json");
    }

    private static void MigrateOldAppData(string oldRoot, string newRoot)
    {
        if (!Directory.Exists(oldRoot) || Directory.Exists(newRoot))
        {
            return;
        }

        Directory.Move(oldRoot, newRoot);
    }

    public AppSettings Load()
    {
        if (!File.Exists(_settingsPath))
        {
            return new AppSettings();
        }

        try
        {
            var text = File.ReadAllText(_settingsPath);
            return JsonSerializer.Deserialize<AppSettings>(text, JsonOptions) ?? new AppSettings();
        }
        catch
        {
            return new AppSettings();
        }
    }

    public void Save(AppSettings settings)
    {
        var tempPath = _settingsPath + ".tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(settings, JsonOptions));
        File.Move(tempPath, _settingsPath, overwrite: true);
    }
}
