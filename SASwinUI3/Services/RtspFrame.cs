namespace SAS.Services;

internal sealed record RtspFrame(byte[] Jpeg, DateTimeOffset CapturedAt);
