using System.Text.Json;
using System.Xml.Linq;
using SAS.Models;

namespace SAS.Services;

public sealed class UserAuthService
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private const string DevAdminNtid = "admin";
    private const string DevAdminPassword = "penAteam";
    private const string SoapUrl = "http://jpetewebapp/jtesw_ws/jtesw_webservice.asmx";

    private readonly string _usersPath;

    public UserAuthService()
    {
        var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SAS");
        Directory.CreateDirectory(root);
        _usersPath = Path.Combine(root, "admins.json");
        var legacyUsersPath = Path.Combine(root, "app_users.json");
        if (!File.Exists(_usersPath) && File.Exists(legacyUsersPath))
        {
            File.Move(legacyUsersPath, _usersPath);
        }
    }

    public bool HasAdmins => LoadUsers().Any(user => user.IsAdmin || string.IsNullOrWhiteSpace(user.Ntid));

    public IReadOnlyList<AppUser> Admins => LoadUsers()
        .Where(user => user.IsAdmin || string.IsNullOrWhiteSpace(user.Ntid))
        .Select(NormalizeLegacyUser)
        .OrderBy(user => user.Ntid)
        .ToList();

    public bool MatchesDeveloperAdmin(string ntid, string password)
    {
        ntid = (ntid ?? string.Empty).Trim();
        password = (password ?? string.Empty).Trim();
        return string.Equals(ntid, DevAdminNtid, StringComparison.OrdinalIgnoreCase)
            && string.Equals(password, DevAdminPassword, StringComparison.Ordinal);
    }

    public AppUser SignIn(string ntid, string password)
    {
        ntid = NormalizeNtid(ntid);
        if (MatchesDeveloperAdmin(ntid, password))
        {
            return new AppUser { Ntid = ntid, IsAdmin = true, CreatedAt = DateTime.UtcNow, LastLoginAt = DateTime.UtcNow };
        }

        ValidateCredentials(ntid, password);

        var users = LoadUsers().Select(NormalizeLegacyUser).ToList();
        var hasAdmins = users.Any(user => user.IsAdmin);
        var existing = users.FirstOrDefault(user => string.Equals(user.Ntid, ntid, StringComparison.OrdinalIgnoreCase));

        if (!hasAdmins)
        {
            existing ??= new AppUser { Ntid = ntid, CreatedAt = DateTime.UtcNow };
            existing.IsAdmin = true;
            existing.LastLoginAt = DateTime.UtcNow;
            users.RemoveAll(user => string.Equals(user.Ntid, ntid, StringComparison.OrdinalIgnoreCase));
            users.Add(existing);
            SaveUsers(users);
            return existing;
        }

        var isAdmin = existing?.IsAdmin == true;
        var sessionUser = existing ?? new AppUser { Ntid = ntid, IsAdmin = false, CreatedAt = DateTime.UtcNow };
        sessionUser.LastLoginAt = DateTime.UtcNow;

        if (existing is not null)
        {
            SaveUsers(users);
        }

        return new AppUser { Ntid = ntid, IsAdmin = isAdmin, LastLoginAt = DateTime.UtcNow };
    }

    public AppUser AddAdmin(string ntid)
    {
        ntid = NormalizeNtid(ntid);
        var users = LoadUsers().Select(NormalizeLegacyUser).ToList();
        var existing = users.FirstOrDefault(user => string.Equals(user.Ntid, ntid, StringComparison.OrdinalIgnoreCase));
        if (existing is null)
        {
            existing = new AppUser { Ntid = ntid, CreatedAt = DateTime.UtcNow };
            users.Add(existing);
        }

        existing.IsAdmin = true;
        SaveUsers(users);
        return existing;
    }

    public void RemoveAdmin(string ntid)
    {
        ntid = NormalizeNtid(ntid);
        var users = LoadUsers().Select(NormalizeLegacyUser).ToList();
        var admins = users.Where(user => user.IsAdmin).ToList();
        if (admins.Count <= 1 && admins.Any(user => string.Equals(user.Ntid, ntid, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException("At least one administrator is required.");
        }

        var existing = users.FirstOrDefault(user => string.Equals(user.Ntid, ntid, StringComparison.OrdinalIgnoreCase));
        if (existing is null || !existing.IsAdmin)
        {
            throw new InvalidOperationException($"{ntid} is not an administrator.");
        }

        users.Remove(existing);
        SaveUsers(users);
    }

    public void ValidateWindowsCredentials(string ntid, string password)
    {
        ntid = NormalizeNtid(ntid);
        if (MatchesDeveloperAdmin(ntid, password))
        {
            return;
        }

        ValidateCredentials(ntid, password);
    }

    public void ValidateNtidExists(string ntid)
    {
        ntid = NormalizeNtid(ntid);
        if (string.Equals(ntid, DevAdminNtid, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (!ActiveDirectorySoapClient.ValidateNtidExistsAsync(ntid).GetAwaiter().GetResult())
        {
            throw new UnauthorizedAccessException("NTID does not exist or the Active Directory service is unreachable.");
        }
    }

    private static void ValidateCredentials(string ntid, string password)
    {
        if (string.IsNullOrWhiteSpace(password))
        {
            throw new UnauthorizedAccessException("Password is required.");
        }

        var result = ActiveDirectorySoapClient.ValidateCredentialsAsync(ntid, password).GetAwaiter().GetResult();
        if (!result.Success)
        {
            throw new UnauthorizedAccessException(result.Message);
        }
    }

    private static string NormalizeNtid(string ntid)
    {
        ntid = ntid.Trim();
        if (ntid.Length < 3)
        {
            throw new InvalidOperationException("NTID must be at least 3 characters.");
        }

        return ntid.ToUpperInvariant();
    }

    private static AppUser NormalizeLegacyUser(AppUser user)
    {
        if (string.IsNullOrWhiteSpace(user.Ntid))
        {
            user.Ntid = string.IsNullOrWhiteSpace(user.UserName) ? user.DisplayName : user.UserName;
            user.IsAdmin = true;
        }

        user.Ntid = user.Ntid.Trim().ToUpperInvariant();
        return user;
    }

    private List<AppUser> LoadUsers()
    {
        if (!File.Exists(_usersPath))
        {
            return [];
        }

        try
        {
            var text = File.ReadAllText(_usersPath);
            return JsonSerializer.Deserialize<List<AppUser>>(text, JsonOptions) ?? [];
        }
        catch
        {
            return [];
        }
    }

    private void SaveUsers(List<AppUser> users)
    {
        var tempPath = _usersPath + ".tmp";
        File.WriteAllText(tempPath, JsonSerializer.Serialize(users, JsonOptions));
        File.Move(tempPath, _usersPath, overwrite: true);
    }

    private static class ActiveDirectorySoapClient
    {
        public static async Task<(bool Success, string Message)> ValidateCredentialsAsync(string ntid, string password)
        {
            ntid = ntid.Trim().ToUpperInvariant();
            if (!await ValidateNtidExistsAsync(ntid).ConfigureAwait(false))
            {
                return (false, "NTID does not exist or the Active Directory service is unreachable.");
            }

            var encrypted = await EncryptPasswordAsync(password).ConfigureAwait(false);
            if (string.IsNullOrWhiteSpace(encrypted))
            {
                return (false, "Password encryption failed or SOAP service is unreachable.");
            }

            return await ValidateEncryptedPasswordAsync(ntid, encrypted).ConfigureAwait(false)
                ? (true, "Login validated successfully.")
                : (false, "Invalid NTID or password.");
        }

        internal static Task<bool> ValidateNtidExistsAsync(string ntid)
        {
            var body = $"""
                <?xml version="1.0" encoding="utf-8"?>
                <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
                  <soap12:Body>
                    <IsUserExistsInAD xmlns="http://jpetewebapp/jtesw_ws/">
                      <userName>{EscapeXml(ntid)}</userName>
                    </IsUserExistsInAD>
                  </soap12:Body>
                </soap12:Envelope>
                """;
            return PostReturnedValueBoolAsync(body, "http://jpetewebapp/jtesw_ws/IsUserExistsInAD");
        }

        private static async Task<string> EncryptPasswordAsync(string password)
        {
            var body = $"""
                <?xml version="1.0" encoding="utf-8"?>
                <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
                  <soap12:Body>
                    <DESEncrypt xmlns="http://jpetewebapp/jtesw_ws/">
                      <sender>{EscapeXml(password)}</sender>
                    </DESEncrypt>
                  </soap12:Body>
                </soap12:Envelope>
                """;

            try
            {
                var text = await PostSoapAsync(body, "").ConfigureAwait(false);
                return FindElementText(text, "DESEncryptResult");
            }
            catch
            {
                return "";
            }
        }

        private static Task<bool> ValidateEncryptedPasswordAsync(string ntid, string encryptedPassword)
        {
            var body = $"""
                <?xml version="1.0" encoding="utf-8"?>
                <soap12:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                                 xmlns:xsd="http://www.w3.org/2001/XMLSchema"
                                 xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
                  <soap12:Body>
                    <ValidateUserCredentialsInAD xmlns="http://jpetewebapp/jtesw_ws/">
                      <userName>{EscapeXml(ntid)}</userName>
                      <password>{EscapeXml(encryptedPassword)}</password>
                    </ValidateUserCredentialsInAD>
                  </soap12:Body>
                </soap12:Envelope>
                """;
            return PostReturnedValueBoolAsync(body, "");
        }

        private static async Task<bool> PostReturnedValueBoolAsync(string body, string soapAction)
        {
            try
            {
                var text = await PostSoapAsync(body, soapAction).ConfigureAwait(false);
                return string.Equals(FindElementText(text, "ReturnedValue"), "true", StringComparison.OrdinalIgnoreCase);
            }
            catch
            {
                return false;
            }
        }

        private static async Task<string> PostSoapAsync(string body, string soapAction)
        {
            using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
            using var request = new HttpRequestMessage(HttpMethod.Post, SoapUrl)
            {
                Content = new StringContent(body, System.Text.Encoding.UTF8, "application/soap+xml")
            };
            if (!string.IsNullOrWhiteSpace(soapAction))
            {
                request.Headers.TryAddWithoutValidation("SOAPAction", soapAction);
            }

            using var response = await client.SendAsync(request).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadAsStringAsync().ConfigureAwait(false);
        }

        private static string FindElementText(string xml, string localName)
        {
            if (string.IsNullOrWhiteSpace(xml))
            {
                return "";
            }

            try
            {
                var doc = XDocument.Parse(xml);
                return doc.Descendants()
                    .FirstOrDefault(element => string.Equals(element.Name.LocalName, localName, StringComparison.OrdinalIgnoreCase))
                    ?.Value
                    ?.Trim() ?? "";
            }
            catch
            {
                return "";
            }
        }

        private static string EscapeXml(string value)
        {
            return System.Security.SecurityElement.Escape(value) ?? "";
        }
    }
}
