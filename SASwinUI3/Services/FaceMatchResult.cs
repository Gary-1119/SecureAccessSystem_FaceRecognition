using SAS.Models;

namespace SAS.Services;

internal sealed record FaceMatchResult(
    FaceUserRecord User,
    double Score,
    double Confidence,
    bool IsAccepted);
