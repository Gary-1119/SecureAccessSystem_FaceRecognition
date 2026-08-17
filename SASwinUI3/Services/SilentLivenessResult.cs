namespace SAS.Services;

internal sealed record SilentLivenessResult(int Count, double Score, bool CanUnlock, string EyeState);
