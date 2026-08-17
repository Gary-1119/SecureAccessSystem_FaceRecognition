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
        _settingsPath = Path.Combine(AppDataPaths.RootDirectory, "settings.json");
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
            var settings = JsonSerializer.Deserialize<AppSettings>(text, JsonOptions) ?? new AppSettings();
            var rtspPassword = ProtectedStringService.Unprotect(settings.RtspPasswordProtected);
            if (!string.IsNullOrEmpty(rtspPassword))
            {
                settings.RtspPassword = rtspPassword;
            }

            return settings;
        }
        catch
        {
            return new AppSettings();
        }
    }

    public void Save(AppSettings settings)
    {
        settings.RtspPasswordProtected = ProtectedStringService.Protect(settings.RtspPassword);
        var tempPath = _settingsPath + ".tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(settings, JsonOptions));
        File.Move(tempPath, _settingsPath, overwrite: true);
    }
}
