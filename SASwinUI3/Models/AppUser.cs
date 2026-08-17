using System.Text.Json.Serialization;

namespace SAS.Models;

public sealed class AppUser
{
    public string Ntid { get; set; } = "";

    public bool IsAdmin { get; set; }

    public DateTime CreatedAt { get; set; } = DateTime.UtcNow;

    public DateTime? LastLoginAt { get; set; }

    // Compatibility with the previous local username/password test store.
    public string UserName { get; set; } = "";

    public string DisplayName { get; set; } = "";

    public string PasswordHash { get; set; } = "";

    public string PasswordSalt { get; set; } = "";

    [JsonIgnore]
    public string EffectiveNtid => string.IsNullOrWhiteSpace(Ntid) ? UserName : Ntid;
}
