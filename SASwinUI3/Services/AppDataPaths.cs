namespace SAS.Services;

public static class AppDataPaths
{
    public const string AppDataFolderName = "SASstream";

    public static string RootDirectory
    {
        get
        {
            var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), AppDataFolderName);
            Directory.CreateDirectory(root);
            return root;
        }
    }
}
