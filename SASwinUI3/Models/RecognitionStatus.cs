namespace SAS.Models;

public sealed record RecognitionStatus(
    bool IsRunning,
    bool StreamHealthy,
    bool ModelReady,
    string ConnectionState,
    string LastError,
    string RtspUrl,
    int ReconnectCount,
    DateTimeOffset? LastFrameAt,
    string? LastMatchedName,
    string? LastMatchedEmployeeId,
    double? LastConfidence);

public sealed record RecognitionUnlockEvent(
    string Name,
    string EmployeeId,
    double Confidence,
    string EventId,
    DateTimeOffset OccurredAt);

public sealed record PreviewFrame(byte[] JpegBytes, DateTimeOffset CapturedAt);

public sealed class FaceUserRecord
{
    public string UserId { get; set; } = Guid.NewGuid().ToString("N");
    public string DisplayName { get; set; } = "";
    public string EmployeeId { get; set; } = "";
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.Now;
    public int SampleCount { get; set; }
    public List<float[]> Embeddings { get; set; } = [];
}

