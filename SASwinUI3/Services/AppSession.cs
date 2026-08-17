namespace SAS.Services;

public static class AppSession
{
    public static string Ntid { get; private set; } = "";

    public static bool IsAdmin { get; private set; }

    public static bool IsAuthenticated => !string.IsNullOrWhiteSpace(Ntid);

    public static void SignIn(string ntid, bool isAdmin)
    {
        Ntid = ntid;
        IsAdmin = isAdmin;
    }

    public static void SignOut()
    {
        Ntid = "";
        IsAdmin = false;
    }
}
