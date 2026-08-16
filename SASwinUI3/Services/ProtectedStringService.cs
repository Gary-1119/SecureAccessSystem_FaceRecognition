using System.Security.Cryptography;
using System.Text;

namespace SAS.Services;

public static class ProtectedStringService
{
    private const DataProtectionScope SharedScope = DataProtectionScope.LocalMachine;

    public static string Protect(string value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return "";
        }

        var plainBytes = Encoding.UTF8.GetBytes(value);
        var protectedBytes = ProtectedData.Protect(plainBytes, optionalEntropy: null, SharedScope);
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
            return UnprotectWithScope(protectedValue, SharedScope);
        }
        catch
        {
            try
            {
                return UnprotectWithScope(protectedValue, DataProtectionScope.CurrentUser);
            }
            catch
            {
                return "";
            }
        }
    }

    private static string UnprotectWithScope(string protectedValue, DataProtectionScope scope)
    {
        var protectedBytes = Convert.FromBase64String(protectedValue);
        var plainBytes = ProtectedData.Unprotect(protectedBytes, optionalEntropy: null, scope);
        return Encoding.UTF8.GetString(plainBytes);
    }
}
