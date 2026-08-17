namespace SAS.Models;

public sealed record PiStorageInfo(
    long TotalBytes,
    long FreeBytes,
    long UsedBytes,
    double UsedPercent,
    string Label)
{
    public static PiStorageInfo Unknown(string label = "Storage unavailable")
    {
        return new PiStorageInfo(0, 0, 0, 0, label);
    }
}
