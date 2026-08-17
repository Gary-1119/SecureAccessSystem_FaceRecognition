namespace SAS.Services;

internal static class RtspUrlMasker
{
    public static string Mask(string url)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || string.IsNullOrWhiteSpace(uri.UserInfo))
        {
            return url;
        }

        var builder = new UriBuilder(uri)
        {
            UserName = "admin",
            Password = "****"
        };
        return builder.Uri.ToString();
    }
}
