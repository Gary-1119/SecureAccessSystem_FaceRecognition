using SAS.Models;

namespace SAS.Services;

public sealed class LocalRtspRecognitionService : IRecognitionService, IJabilEyeTransferService
{
    private static readonly TimeSpan RecognitionFrameInterval = TimeSpan.FromMilliseconds(60);

    private readonly AppLogService _log;
    private readonly object _gate = new();
    private readonly FaceDataStore _faceData;
    private readonly FaceRecognitionEngine _faceEngine = new();
    private readonly FaceMatcher _faceMatcher = new();
    private readonly RtspFrameReader _frameReader = new();
    private readonly SilentBlinkLivenessService _liveness = new();
    private readonly RecognitionStatusStore _statusStore = new();

    private AppSettings _settings = new();
    private CancellationTokenSource? _runCts;
    private Task? _cameraTask;
    private Task? _recognitionTask;
    private byte[]? _latestJpeg;
    private byte[]? _latestRecognitionJpeg;
    private DateTimeOffset _lastUnlockAt = DateTimeOffset.MinValue;
    private string _lockSessionId = "";

    public LocalRtspRecognitionService(AppLogService log)
    {
        _log = log;
        _faceData = new FaceDataStore(log);
    }

    public event EventHandler<RecognitionStatus>? StatusChanged;
    public event EventHandler<RecognitionUnlockEvent>? UnlockRecognized;
    public event EventHandler<PreviewFrame>? PreviewFrameAvailable;

    public RecognitionStatus CurrentStatus
    {
        get
        {
            lock (_gate)
            {
                return _statusStore.Current;
            }
        }
    }

    public IReadOnlyList<FaceUserRecord> Users
    {
        get
        {
            lock (_gate)
            {
                return _faceData.Users;
            }
        }
    }

    public async Task ConfigureAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        var next = settings.Clone();
        next.CameraSource = "rtsp";
        if (string.IsNullOrWhiteSpace(next.RtspUser))
        {
            next.RtspUser = "admin";
        }

        next.RtspPort = 8554;
        next.RtspPath = "jabileye-stream";
        var wasRunning = _runCts is not null;
        var sameRtspUrl = string.Equals(next.RtspUrl, _settings.RtspUrl, StringComparison.OrdinalIgnoreCase);
        if (wasRunning && !sameRtspUrl)
        {
            await StopAsync(cancellationToken).ConfigureAwait(false);
            wasRunning = false;
        }

        _settings = next;
        lock (_gate)
        {
            _faceData.Reload();
        }

        var error = string.IsNullOrWhiteSpace(_settings.JabilEyeHost) ? "Camera hostname/IP is required." : "";
        if (!wasRunning)
        {
            PublishStatus(_statusStore.SetConnection(false, false, true, string.IsNullOrWhiteSpace(error) ? "configured" : "disconnected", error, RtspUrlMasker.Mask(_settings.RtspUrl)));
        }
        else if (!sameRtspUrl)
        {
            PublishStatus(_statusStore.SetConnection(true, false, true, "rtsp reconnecting", "Camera settings changed; reconnecting stream.", RtspUrlMasker.Mask(_settings.RtspUrl)));
        }
    }

    public Task StartAsync(CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(_settings.JabilEyeHost))
        {
            PublishStatus(_statusStore.SetConnection(false, false, true, "disconnected", "Camera hostname/IP is required.", ""));
            return Task.CompletedTask;
        }

        if (_runCts is not null)
        {
            return Task.CompletedTask;
        }

        _runCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        PublishStatus(_statusStore.SetConnection(true, false, true, "connecting", "", RtspUrlMasker.Mask(_settings.RtspUrl)));
        _cameraTask = Task.Run(() => CameraLoopAsync(_runCts.Token), CancellationToken.None);
        _recognitionTask = Task.Run(() => RecognitionLoopAsync(_runCts.Token), CancellationToken.None);
        _log.Write($"RTSP recognition started: {RtspUrlMasker.Mask(_settings.RtspUrl)}");
        return Task.CompletedTask;
    }

    public async Task StopAsync(CancellationToken cancellationToken = default)
    {
        var cts = _runCts;
        _runCts = null;
        cts?.Cancel();
        try
        {
            if (_cameraTask is not null)
            {
                await _cameraTask.WaitAsync(TimeSpan.FromSeconds(3), cancellationToken).ConfigureAwait(false);
            }

            if (_recognitionTask is not null)
            {
                await _recognitionTask.WaitAsync(TimeSpan.FromSeconds(3), cancellationToken).ConfigureAwait(false);
            }
        }
        catch
        {
        }
        finally
        {
            cts?.Dispose();
            _cameraTask = null;
            _recognitionTask = null;
            PublishStatus(_statusStore.SetConnection(false, false, true, "sas preview stopped", "", RtspUrlMasker.Mask(_settings.RtspUrl)));
        }
    }

    public Task<FaceUserRecord> RegisterCurrentFaceAsync(string displayName, string employeeId, CancellationToken cancellationToken = default)
    {
        displayName = (displayName ?? "").Trim();
        employeeId = (employeeId ?? "").Trim().ToUpperInvariant();
        if (string.IsNullOrWhiteSpace(displayName))
        {
            throw new InvalidOperationException("Employee name is required.");
        }

        if (string.IsNullOrWhiteSpace(employeeId))
        {
            throw new InvalidOperationException("Employee ID / NTID is required.");
        }

        byte[] jpeg;
        lock (_gate)
        {
            jpeg = _latestJpeg?.ToArray() ?? throw new InvalidOperationException("No camera frame is available. Open the camera and try again.");
        }

        var embedding = _faceEngine.GenerateBestEmbedding(jpeg).Embedding;
        FaceUserRecord user;
        lock (_gate)
        {
            user = _faceData.AddSample(displayName, employeeId, embedding, jpeg);
        }

        _log.Write($"Local face captured: {displayName} / {employeeId}, samples={user.SampleCount}.");
        return Task.FromResult(user);
    }

    public Task<bool> DeleteUserAsync(string employeeId, CancellationToken cancellationToken = default)
    {
        employeeId = (employeeId ?? "").Trim().ToUpperInvariant();
        if (string.IsNullOrWhiteSpace(employeeId))
        {
            throw new InvalidOperationException("Employee ID / NTID is required.");
        }

        var removed = false;
        lock (_gate)
        {
            removed = _faceData.Delete(employeeId);
        }

        return Task.FromResult(removed);
    }

    public Task<string> ExportFaceDataAsync(string folder, CancellationToken cancellationToken = default)
    {
        return ExportFaceDataToLocalAsync(folder, cancellationToken);
    }

    public Task<int> ImportFaceDataAsync(string zipPath, CancellationToken cancellationToken = default)
    {
        return ImportFaceDataFromLocalAsync(zipPath, cancellationToken);
    }

    public Task<int> RestoreLatestImportBackupAsync(CancellationToken cancellationToken = default)
    {
        throw new InvalidOperationException("Restore latest import backup is not available in RTSP mode.");
    }

    public void ResetUnlockCooldown()
    {
        _lockSessionId = Guid.NewGuid().ToString("N");
        _lastUnlockAt = DateTimeOffset.MinValue;
    }

    public void EndUnlockSession(string reason = "unlocked")
    {
        _lockSessionId = "";
    }

    public void SimulateAuthorizedFace(string name = "Authorized User", string employeeId = "LOCAL")
    {
        UnlockRecognized?.Invoke(this, new RecognitionUnlockEvent(name, employeeId, 99, Guid.NewGuid().ToString("N"), DateTimeOffset.Now));
    }

    public Task MountServerAsync(AppSettings settings, bool save, CancellationToken cancellationToken = default)
    {
        if (!string.IsNullOrWhiteSpace(settings.ServerPath))
        {
            Directory.CreateDirectory(settings.ServerPath);
            Directory.CreateDirectory(Path.Combine(settings.ServerPath, "SAS_LOG"));
        }

        return Task.CompletedTask;
    }

    public Task SetCameraRotationAsync(int cameraRotation, CancellationToken cancellationToken = default)
    {
        lock (_gate)
        {
            _settings.CameraRotation = RtspFrameReader.NormalizeRotation(cameraRotation);
        }

        return Task.CompletedTask;
    }

    public async Task<string> ExportFaceDataToServerAsync(AppSettings settings, string? serverFolder = null, CancellationToken cancellationToken = default)
    {
        var folder = string.IsNullOrWhiteSpace(serverFolder) ? settings.ServerPath : serverFolder;
        return await ExportFaceDataToLocalAsync(folder ?? "", cancellationToken).ConfigureAwait(false);
    }

    public Task<string> ExportFaceDataToLocalAsync(string localFolder, CancellationToken cancellationToken = default)
    {
        localFolder = (localFolder ?? "").Trim();
        if (string.IsNullOrWhiteSpace(localFolder))
        {
            throw new InvalidOperationException("Choose an export folder.");
        }

        string zipPath;
        lock (_gate)
        {
            zipPath = _faceData.ExportToLocal(localFolder);
        }

        return Task.FromResult(zipPath);
    }

    public Task<int> ImportFaceDataFromServerAsync(string zipPath, CancellationToken cancellationToken = default)
    {
        return ImportFaceDataFromLocalAsync(zipPath, cancellationToken);
    }

    public Task<int> ImportFaceDataFromLocalAsync(string localZipPath, CancellationToken cancellationToken = default)
    {
        int added;
        lock (_gate)
        {
            added = _faceData.ImportFromLocal(localZipPath);
        }

        return Task.FromResult(added);
    }

    private async Task CameraLoopAsync(CancellationToken cancellationToken)
    {
        var reconnectDelay = TimeSpan.FromSeconds(2);
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                var rtspUrl = _settings.RtspUrl;
                var displayUrl = RtspUrlMasker.Mask(rtspUrl);
                await _frameReader.ReadAsync(
                    rtspUrl,
                    GetCameraRotation,
                    () => PublishStatus(_statusStore.SetConnection(true, true, true, "live", "", displayUrl)),
                    OnRtspFrame,
                    cancellationToken).ConfigureAwait(false);
                reconnectDelay = TimeSpan.FromSeconds(2);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                PublishStatus(_statusStore.SetConnection(true, false, true, "rtsp reconnecting", ex.Message, RtspUrlMasker.Mask(_settings.RtspUrl), incrementReconnect: true));
                await Task.Delay(reconnectDelay, cancellationToken).ConfigureAwait(false);
                reconnectDelay = TimeSpan.FromSeconds(Math.Min(reconnectDelay.TotalSeconds * 2, 15));
            }
        }
    }

    private int GetCameraRotation()
    {
        lock (_gate)
        {
            return _settings.CameraRotation;
        }
    }

    private void OnRtspFrame(RtspFrame frame)
    {
        lock (_gate)
        {
            _latestJpeg = frame.Jpeg.ToArray();
            _latestRecognitionJpeg = _latestJpeg.ToArray();
        }

        OnPreviewFrameAvailable(frame.Jpeg, frame.CapturedAt);
    }

    private async Task RecognitionLoopAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            byte[]? jpeg;
            lock (_gate)
            {
                jpeg = _latestRecognitionJpeg;
                _latestRecognitionJpeg = null;
            }

            if (jpeg is not null)
            {
                TryRecognize(jpeg);
            }

            await Task.Delay(RecognitionFrameInterval, cancellationToken).ConfigureAwait(false);
        }
    }

    private void TryRecognize(byte[] jpeg)
    {
        List<FaceUserRecord> users;
        lock (_gate)
        {
            users = _faceData.UsersWithEmbeddings();
        }

        if (users.Count == 0 || DateTimeOffset.Now - _lastUnlockAt < TimeSpan.FromSeconds(4))
        {
            return;
        }

        FaceEmbeddingResult embedding;
        try
        {
            embedding = _faceEngine.GenerateBestEmbedding(jpeg);
        }
        catch
        {
            SetUnknownMatch(null);
            return;
        }

        var best = _faceMatcher.FindBest(users, embedding.Embedding);
        if (best is null)
        {
            _liveness.Reset();
            SetUnknownMatch(null, embedding.FaceBox);
            return;
        }

        if (!best.IsAccepted)
        {
            _liveness.Reset();
            SetUnknownMatch(best.Confidence, embedding.FaceBox);
            return;
        }

        if (embedding.FaceBox is null)
        {
            _liveness.Reset();
            SetLivenessRejected(best.User, best.Confidence, null, null, "Live check unavailable");
            return;
        }

        var now = DateTimeOffset.Now;
        var liveness = _liveness.RecordBlink(best.User.EmployeeId, embedding.EyeState, now);
        SetLastMatch(best.User, best.Confidence, embedding.FaceBox, liveness);
        if (!liveness.CanUnlock)
        {
            return;
        }

        _liveness.Reset();
        _lastUnlockAt = now;
        var eventId = $"{_lockSessionId}|{best.User.EmployeeId}|{_lastUnlockAt:yyyyMMddHHmmss}";
        UnlockRecognized?.Invoke(this, new RecognitionUnlockEvent(best.User.DisplayName, best.User.EmployeeId, best.Confidence, eventId, _lastUnlockAt));
    }

    private void OnPreviewFrameAvailable(byte[] jpeg, DateTimeOffset capturedAt)
    {
        var status = _statusStore.MarkPreviewLive(RtspUrlMasker.Mask(_settings.RtspUrl), capturedAt, out var notifyStatus);

        if (notifyStatus)
        {
            PublishStatus(status);
        }

        PreviewFrameAvailable?.Invoke(this, new PreviewFrame(jpeg, capturedAt));
    }

    private void SetLastMatch(FaceUserRecord user, double confidence, RecognitionFaceBox? faceBox, SilentLivenessResult liveness)
    {
        PublishStatus(_statusStore.SetLastMatch(user, confidence, faceBox, liveness));
    }

    private void SetLivenessRejected(FaceUserRecord user, double confidence, double? livenessScore, RecognitionFaceBox? faceBox, string message)
    {
        _log.Write(livenessScore is null
            ? $"Unlock blocked: {message}"
            : $"Unlock blocked: {message}; motion score {livenessScore:0.0}%.");
        PublishStatus(_statusStore.SetLivenessRejected(user, confidence, livenessScore, faceBox, message));
    }

    private void SetUnknownMatch(double? confidence, RecognitionFaceBox? faceBox = null)
    {
        if (_statusStore.TrySetUnknown(confidence, faceBox, out var status))
        {
            PublishStatus(status);
        }
    }

    private void PublishStatus(RecognitionStatus status)
    {
        StatusChanged?.Invoke(this, status);
    }

    public void Dispose()
    {
        _runCts?.Cancel();
        _runCts?.Dispose();
    }
}
