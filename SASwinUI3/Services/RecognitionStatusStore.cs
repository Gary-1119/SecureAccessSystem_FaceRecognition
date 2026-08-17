using SAS.Models;

namespace SAS.Services;

internal sealed class RecognitionStatusStore
{
    private readonly object _gate = new();
    private RecognitionStatus _status = new(false, false, true, "stopped", "", "", 0, null, null, null, null);
    private DateTimeOffset _lastPreviewStatusAt = DateTimeOffset.MinValue;
    private DateTimeOffset _lastUnknownAt = DateTimeOffset.MinValue;

    public RecognitionStatus Current
    {
        get
        {
            lock (_gate)
            {
                return _status;
            }
        }
    }

    public RecognitionStatus SetConnection(bool isRunning, bool healthy, bool modelReady, string state, string error, string url, bool incrementReconnect = false)
    {
        lock (_gate)
        {
            _status = _status with
            {
                IsRunning = isRunning,
                StreamHealthy = healthy,
                ModelReady = modelReady,
                ConnectionState = state,
                LastError = error,
                RtspUrl = url,
                ReconnectCount = _status.ReconnectCount + (incrementReconnect ? 1 : 0),
                LastFrameAt = isRunning ? _status.LastFrameAt : null
            };
            return _status;
        }
    }

    public RecognitionStatus MarkPreviewLive(string rtspUrl, DateTimeOffset capturedAt, out bool shouldNotify)
    {
        lock (_gate)
        {
            shouldNotify = !_status.StreamHealthy ||
                !_status.ConnectionState.Equals("live", StringComparison.OrdinalIgnoreCase) ||
                capturedAt - _lastPreviewStatusAt >= TimeSpan.FromSeconds(1);
            _status = _status with
            {
                StreamHealthy = true,
                ConnectionState = "live",
                LastError = "",
                LastFrameAt = capturedAt,
                RtspUrl = rtspUrl
            };

            if (shouldNotify)
            {
                _lastPreviewStatusAt = capturedAt;
            }

            return _status;
        }
    }

    public RecognitionStatus SetLastMatch(FaceUserRecord user, double confidence, RecognitionFaceBox? faceBox, SilentLivenessResult liveness)
    {
        lock (_gate)
        {
            _status = _status with
            {
                LastMatchedName = user.DisplayName,
                LastMatchedEmployeeId = user.EmployeeId,
                LastConfidence = confidence,
                LastLivenessScore = liveness.Score,
                LastLivenessPassed = liveness.CanUnlock,
                LastLivenessMessage = liveness.CanUnlock
                    ? "Live"
                    : $"Waiting for natural blink ({liveness.EyeState})",
                FaceBox = faceBox
            };
            return _status;
        }
    }

    public RecognitionStatus SetLivenessRejected(FaceUserRecord user, double confidence, double? livenessScore, RecognitionFaceBox? faceBox, string message)
    {
        lock (_gate)
        {
            _status = _status with
            {
                LastMatchedName = user.DisplayName,
                LastMatchedEmployeeId = user.EmployeeId,
                LastConfidence = confidence,
                LastLivenessScore = livenessScore,
                LastLivenessPassed = false,
                LastLivenessMessage = message,
                FaceBox = faceBox
            };
            return _status;
        }
    }

    public bool TrySetUnknown(double? confidence, RecognitionFaceBox? faceBox, out RecognitionStatus status)
    {
        lock (_gate)
        {
            if (DateTimeOffset.Now - _lastUnknownAt < TimeSpan.FromSeconds(1))
            {
                status = _status;
                return false;
            }

            _lastUnknownAt = DateTimeOffset.Now;
            _status = _status with
            {
                LastMatchedName = "Unknown",
                LastMatchedEmployeeId = "",
                LastConfidence = confidence,
                LastLivenessScore = null,
                LastLivenessPassed = null,
                LastLivenessMessage = null,
                FaceBox = faceBox
            };
            status = _status;
            return true;
        }
    }
}
