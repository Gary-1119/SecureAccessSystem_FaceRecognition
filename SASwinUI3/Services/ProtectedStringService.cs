using System.Security.Cryptography;
using System.Text;

namespace SAS.Services;

public static class ProtectedStringService
{
    public static string Protect(string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return "";
        }

        var plainBytes = Encoding.UTF8.GetBytes(value);
        var protectedBytes = ProtectedData.Protect(plainBytes, optionalEntropy: null, DataProtectionScope.CurrentUser);
        return Convert.ToBase64String(protectedBytes);
    }

    public static string Unprotect(string protectedValue)
    {
        if (string.IsNullOrWhiteSpace(protectedValue))
        {
            return "";
        }

        try
        {
            var protectedBytes = Convert.FromBase64String(protectedValue);
            var plainBytes = ProtectedData.Unprotect(protectedBytes, optionalEntropy: null, DataProtectionScope.CurrentUser);
            return Encoding.UTF8.GetString(plainBytes);
        }
        catch
        {
            return "";
        }
    }
}
