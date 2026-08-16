using SAS.Models;

namespace SAS.Services;

internal sealed class FaceMatcher
{
    private const double MatchThreshold = 0.42;
    private const double MinimumRecognitionConfidence = 65d;

    public FaceMatchResult? FindBest(IReadOnlyList<FaceUserRecord> users, float[] embedding)
    {
        var best = users
            .SelectMany(user => user.Embeddings.Select(sample => new { User = user, Score = Dot(embedding, sample) }))
            .OrderByDescending(match => match.Score)
            .FirstOrDefault();
        if (best is null)
        {
            return null;
        }

        var confidence = best.Score * 100d;
        return new FaceMatchResult(
            best.User,
            best.Score,
            confidence,
            best.Score >= MatchThreshold && confidence >= MinimumRecognitionConfidence);
    }

    private static double Dot(float[] a, float[] b)
    {
        var length = Math.Min(a.Length, b.Length);
        var sum = 0d;
        for (var i = 0; i < length; i++)
        {
            sum += a[i] * b[i];
        }

        return sum;
    }
}
