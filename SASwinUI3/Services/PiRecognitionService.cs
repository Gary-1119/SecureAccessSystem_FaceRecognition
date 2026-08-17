using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text.Json.Nodes;
using SAS.Models;

namespace SAS.Services;

public interface IPiTransferService
{
    Task MountServerAsync(AppSettings settings, bool save, CancellationToken cancellationToken = default);
    Task SetCameraRotationAsync(int cameraRotation, CancellationToken cancellationToken = default);
    Task<string> ExportFaceDataToServerAsync(AppSettings settings, string? serverFolder = null, CancellationToken cancellationToken = default);
    Task<string> ExportFaceDataToLocalAsync(string localFolder, CancellationToken cancellationToken = default);
    Task<int> ImportFaceDataFromServerAsync(string zipPath, CancellationToken cancellationToken = default);
    Task<int> ImportFaceDataFromLocalAsync(string localZipPath, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<string>> ListSftpTargetsAsync(CancellationToken cancellationToken = default);
    Task AddSftpTargetAsync(string hostname, bool requireReachable = true, CancellationToken cancellationToken = default);
    Task RemoveSftpTargetAsync(string hostname, CancellationToken cancellationToken = default);
    Task<string> StartMultiSftpTransferAsync(IEnumerable<string> targets, CancellationToken cancellationToken = default);
    Task<JsonObject> GetMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default);
    Task<JsonObject> CancelMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default);
    Task<IReadOnlyList<string>> ListReceivedAsync(CancellationToken cancellationToken = default);
    Task<int> AcceptReceivedAsync(string filename, CancellationToken cancellationToken = default);
    Task RejectReceivedAsync(string filename, CancellationToken cancellationToken = default);
    Task<PiStorageInfo> GetStorageInfoAsync(CancellationToken cancellationToken = default);
    Task<IReadOnlyList<string>> GetPiLogsAsync(CancellationToken cancellationToken = default);
    Task ClearPiLogsAsync(CancellationToken cancellationToken = default);
}

public sealed class PiRecognitionService : IRecognitionService, IPiTransferService
{
    private readonly AppLogService _log;
    private readonly PiApiClient _api = new();
    private readonly PiPreviewStreamClient _previewStream = new();
    private readonly PiWebSocketClient _webSocketClient = new();
    private readonly PiSftpFileTransferService _sftpFileTransfer = new();
    private readonly PiFaceDataApi _faceDataApi;
    private readonly object _gate = new();
    private readonly ConcurrentDictionary<string, byte> _seenUnlockEvents = new(StringComparer.OrdinalIgnoreCase);

    private AppSettings _settings = new();
    private CancellationTokenSource? _runCts;
    private Task? _webSocketTask;
    private Task? _previewTask;
    private Task? _statusTask;
    private ClientWebSocket? _activeSocket;
    private List<FaceUserRecord> _users = [];
    private RecognitionStatus _status = new(false, false, false, "stopped", "", "", 0, null, null, null, null);
    private string _lockSessionId = "";
    private int _statusFailureCount;
    private volatile bool _sasSessionAccepted;

    public event EventHandler<RecognitionStatus>? StatusChanged;
    public event EventHandler<RecognitionUnlockEvent>? UnlockRecognized;
    public event EventHandler<PreviewFrame>? PreviewFrameAvailable;

    public PiRecognitionService(AppLogService log)
    {
        _log = log;
        _faceDataApi = new PiFaceDataApi(_api, _sftpFileTransfer, GetPiSftpCredentialsAsync, RefreshUsersFromPiAsync, () => _settings.PiHost);
    }

    public RecognitionStatus CurrentStatus
    {
        get
        {
            lock (_gate)
            {
                return _status;
            }
        }
    }

    public IReadOnlyList<FaceUserRecord> Users
    {
        get
        {
            lock (_gate)
            {
                return _users.Select(CloneUser).ToList();
            }
        }
    }

    public async Task ConfigureAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        var nextSettings = settings.Clone();
        if (_runCts is not null &&
            !string.Equals(_settings.ApiBaseUrl, nextSettings.ApiBaseUrl, StringComparison.OrdinalIgnoreCase))
        {
            await StopAsync(cancellationToken).ConfigureAwait(false);
        }

        _settings = nextSettings;
        EnsureClientId();
        _api.Configure(_settings.ApiBaseUrl);
        SetStatus(false, false, true, "disconnected", string.IsNullOrWhiteSpace(_settings.PiHost) ? "Pi hostname/IP is required." : "", _settings.ApiBaseUrl);
        if (string.IsNullOrWhiteSpace(_settings.PiHost))
        {
            return;
        }

        try
        {
            await RefreshUsersFromPiAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            SetStatus(false, false, true, "disconnected", ex.Message, _settings.ApiBaseUrl, incrementReconnect: true);
        }
    }

    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(_settings.PiHost))
        {
            SetStatus(false, false, true, "disconnected", "Pi hostname/IP is required.", "");
            return;
        }

        if (_runCts is not null)
        {
            return;
        }

        _runCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        _statusFailureCount = 0;
        SetStatus(true, false, true, "connecting", "", _settings.ApiBaseUrl);

        try
        {
            await EnsureSasSessionAcceptedAsync(_runCts.Token).ConfigureAwait(false);
            SetStatus(true, true, true, "connected", "", _settings.ApiBaseUrl);
        }
        catch (Exception ex)
        {
            _log.Write($"Pi recognition start warning: {ex.Message}");
            _sasSessionAccepted = false;
            SetStatus(true, false, true, "disconnected", ex.Message, _settings.ApiBaseUrl, incrementReconnect: true);
        }

        _webSocketTask = Task.Run(() => WebSocketLoopAsync(_runCts.Token), CancellationToken.None);
        _previewTask = Task.Run(() => PreviewLoopAsync(_runCts.Token), CancellationToken.None);
        _statusTask = Task.Run(() => StatusLoopAsync(_runCts.Token), CancellationToken.None);
        _log.Write("Pi WebSocket/API recognition started.");
    }

    public async Task StopAsync(CancellationToken cancellationToken = default)
    {
        var cts = _runCts;
        _runCts = null;
        cts?.Cancel();

        try
        {
            await SasDisconnectAsync(force: false, cancellationToken).ConfigureAwait(false);
        }
        catch
        {
        }

        _sasSessionAccepted = false;
        _statusFailureCount = 0;
        await WaitQuietlyAsync(_webSocketTask, cancellationToken).ConfigureAwait(false);
        await WaitQuietlyAsync(_previewTask, cancellationToken).ConfigureAwait(false);
        await WaitQuietlyAsync(_statusTask, cancellationToken).ConfigureAwait(false);
        cts?.Dispose();
        _activeSocket = null;
        SetStatus(false, false, true, "sas preview stopped", "", _settings.ApiBaseUrl);
    }

    public async Task<FaceUserRecord> RegisterCurrentFaceAsync(string displayName, string employeeId, CancellationToken cancellationToken = default)
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

        var data = await RequestAsync(
            "POST",
            "/capture-user",
            new JsonObject
            {
                ["user_id"] = employeeId,
                ["employee_id"] = employeeId,
                ["display_name"] = displayName,
                ["name"] = displayName,
                ["mode"] = "add",
                ["auto_capture"] = false
            },
            timeoutSeconds: 120,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        await TryPostAsync("/train", timeoutSeconds: 120, cancellationToken).ConfigureAwait(false);
        await RefreshUsersFromPiAsync(cancellationToken).ConfigureAwait(false);
        var user = Users.FirstOrDefault(u => string.Equals(u.EmployeeId, employeeId, StringComparison.OrdinalIgnoreCase));
        return user ?? new FaceUserRecord { EmployeeId = employeeId, DisplayName = displayName, SampleCount = ReadInt(data, "photos", "sample_count", "samples") };
    }

    public async Task<bool> DeleteUserAsync(string employeeId, CancellationToken cancellationToken = default)
    {
        employeeId = (employeeId ?? "").Trim().ToUpperInvariant();
        if (string.IsNullOrWhiteSpace(employeeId))
        {
            throw new InvalidOperationException("Employee ID / NTID is required.");
        }

        await RequestAsync(
            "POST",
            "/delete-user",
            new JsonObject
            {
                ["user_id"] = employeeId,
                ["employee_id"] = employeeId
            },
            timeoutSeconds: 60,
            cancellationToken: cancellationToken).ConfigureAwait(false);
        await RefreshUsersFromPiAsync(cancellationToken).ConfigureAwait(false);
        return true;
    }

    public async Task<string> ExportFaceDataAsync(string folder, CancellationToken cancellationToken = default)
    {
        return await ExportFaceDataToServerAsync(_settings, folder, cancellationToken).ConfigureAwait(false);
    }

    public async Task<int> ImportFaceDataAsync(string zipPath, CancellationToken cancellationToken = default)
    {
        return await ImportFaceDataFromServerAsync(zipPath, cancellationToken).ConfigureAwait(false);
    }

    public Task<int> RestoreLatestImportBackupAsync(CancellationToken cancellationToken = default)
    {
        throw new InvalidOperationException("Restore latest backup is handled on the Pi by importing or accepting a received package. No restore endpoint is exposed by the v107 Pi API.");
    }

    public void ResetUnlockCooldown()
    {
        _seenUnlockEvents.Clear();
        _lockSessionId = Guid.NewGuid().ToString("N");
        _ = SendWsSessionNoticeAsync("lock_session_started", "locked");
    }

    public void EndUnlockSession(string reason = "unlocked")
    {
        if (string.IsNullOrWhiteSpace(_lockSessionId))
        {
            return;
        }

        _ = SendWsSessionNoticeAsync("lock_session_ended", reason);
        _lockSessionId = "";
    }

    public void SimulateAuthorizedFace(string name = "Authorized User", string employeeId = "LOCAL")
    {
        UnlockRecognized?.Invoke(this, new RecognitionUnlockEvent(name, employeeId, 99, Guid.NewGuid().ToString("N"), DateTimeOffset.Now));
    }

    public async Task MountServerAsync(AppSettings settings, bool save, CancellationToken cancellationToken = default)
    {
        await _faceDataApi.MountServerAsync(settings, save, cancellationToken).ConfigureAwait(false);
    }

    public async Task SetCameraRotationAsync(int cameraRotation, CancellationToken cancellationToken = default)
    {
        await _faceDataApi.SetCameraRotationAsync(cameraRotation, cancellationToken).ConfigureAwait(false);
    }

    public async Task<string> ExportFaceDataToServerAsync(AppSettings settings, string? serverFolder = null, CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.ExportFaceDataToServerAsync(settings, cancellationToken).ConfigureAwait(false);
    }

    public async Task<string> ExportFaceDataToLocalAsync(string localFolder, CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.ExportFaceDataToLocalAsync(localFolder, cancellationToken).ConfigureAwait(false);
    }

    public async Task<int> ImportFaceDataFromServerAsync(string zipPath, CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.ImportFaceDataFromServerAsync(zipPath, cancellationToken).ConfigureAwait(false);
    }

    public async Task<int> ImportFaceDataFromLocalAsync(string localZipPath, CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.ImportFaceDataFromLocalAsync(localZipPath, cancellationToken).ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<string>> ListSftpTargetsAsync(CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.ListSftpTargetsAsync(cancellationToken).ConfigureAwait(false);
    }

    public async Task AddSftpTargetAsync(string hostname, bool requireReachable = true, CancellationToken cancellationToken = default)
    {
        await _faceDataApi.AddSftpTargetAsync(hostname, requireReachable, cancellationToken).ConfigureAwait(false);
    }

    public async Task RemoveSftpTargetAsync(string hostname, CancellationToken cancellationToken = default)
    {
        await _faceDataApi.RemoveSftpTargetAsync(hostname, cancellationToken).ConfigureAwait(false);
    }

    public async Task<string> StartMultiSftpTransferAsync(IEnumerable<string> targets, CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.StartMultiSftpTransferAsync(targets, cancellationToken).ConfigureAwait(false);
    }

    public Task<JsonObject> GetMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default)
    {
        return _faceDataApi.GetMultiSftpTransferAsync(batchId, cancellationToken);
    }

    public Task<JsonObject> CancelMultiSftpTransferAsync(string batchId, CancellationToken cancellationToken = default)
    {
        return _faceDataApi.CancelMultiSftpTransferAsync(batchId, cancellationToken);
    }

    public async Task<IReadOnlyList<string>> ListReceivedAsync(CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.ListReceivedAsync(cancellationToken).ConfigureAwait(false);
    }

    public async Task<int> AcceptReceivedAsync(string filename, CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.AcceptReceivedAsync(filename, cancellationToken).ConfigureAwait(false);
    }

    public async Task RejectReceivedAsync(string filename, CancellationToken cancellationToken = default)
    {
        await _faceDataApi.RejectReceivedAsync(filename, cancellationToken).ConfigureAwait(false);
    }

    public async Task<PiStorageInfo> GetStorageInfoAsync(CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.GetStorageInfoAsync(cancellationToken).ConfigureAwait(false);
    }

    public async Task<IReadOnlyList<string>> GetPiLogsAsync(CancellationToken cancellationToken = default)
    {
        return await _faceDataApi.GetPiLogsAsync(cancellationToken).ConfigureAwait(false);
    }

    public async Task ClearPiLogsAsync(CancellationToken cancellationToken = default)
    {
        await _faceDataApi.ClearPiLogsAsync(cancellationToken).ConfigureAwait(false);
    }

    private async Task StatusLoopAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                if (!_sasSessionAccepted)
                {
                    await EnsureSasSessionAcceptedAsync(cancellationToken).ConfigureAwait(false);
                }

                var data = await RequestAsync("GET", "/status", timeoutSeconds: 8, cancellationToken: cancellationToken).ConfigureAwait(false);
                TryRaiseUnlockFromJson(data);
                await RefreshUsersFromPiAsync(cancellationToken).ConfigureAwait(false);
                var running = ReadBool(data, "recognition_running", "running", "is_running");
                var state = running ? "live" : "connected";
                _statusFailureCount = 0;
                SetStatus(true, true, true, state, "", _settings.ApiBaseUrl);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _statusFailureCount++;
                if (_sasSessionAccepted && _statusFailureCount < 3)
                {
                    SetStatus(true, true, true, "connected", $"API reconnecting: {ex.Message}", _settings.ApiBaseUrl, incrementReconnect: true);
                }
                else
                {
                    _sasSessionAccepted = false;
                    SetStatus(true, false, true, "disconnected", ex.Message, _settings.ApiBaseUrl, incrementReconnect: true);
                }
            }

            await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken).ConfigureAwait(false);
        }
    }

    private async Task PreviewLoopAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            if (!_sasSessionAccepted)
            {
                await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken).ConfigureAwait(false);
                continue;
            }

            try
            {
                await _previewStream.RunAsync(_settings.ApiBaseUrl, OnPreviewFrameAvailable, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                if (_sasSessionAccepted)
                {
                    SetStatus(true, true, true, "connected", $"Camera preview reconnecting: {ex.Message}", _settings.ApiBaseUrl, incrementReconnect: true);
                }
                await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken).ConfigureAwait(false);
            }
        }
    }

    private async Task WebSocketLoopAsync(CancellationToken cancellationToken)
    {
        var delay = TimeSpan.FromMilliseconds(1500);
        while (!cancellationToken.IsCancellationRequested)
        {
            if (!_sasSessionAccepted)
            {
                await Task.Delay(TimeSpan.FromSeconds(1), cancellationToken).ConfigureAwait(false);
                continue;
            }

            ClientWebSocket? socket = null;
            try
            {
                var uri = PiWebSocketClient.BuildUri(_settings.PiHost, _settings.ApiPort, _settings.ClientId, _settings.ClientName);
                SetStatus(true, true, true, "connected", "", _settings.ApiBaseUrl);
                socket = await _webSocketClient.ConnectAsync(uri, cancellationToken).ConfigureAwait(false);
                delay = TimeSpan.FromMilliseconds(1500);
                SetStatus(true, true, true, "live", "", _settings.ApiBaseUrl);
                _activeSocket = socket;
                await PiWebSocketClient.SendAsync(socket, new JsonObject
                {
                    ["type"] = "hello",
                    ["client"] = "Windows SAS",
                    ["client_id"] = _settings.ClientId,
                    ["client_name"] = _settings.ClientName,
                    ["role"] = "recognition_unlock"
                }, cancellationToken).ConfigureAwait(false);
                if (!string.IsNullOrWhiteSpace(_lockSessionId))
                {
                    await SendWsSessionNoticeAsync("lock_session_started", "locked", cancellationToken).ConfigureAwait(false);
                }

                await PiWebSocketClient.ReceiveTextMessagesAsync(socket, HandleWebSocketMessage, cancellationToken).ConfigureAwait(false);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                if (socket is not null && ReferenceEquals(_activeSocket, socket))
                {
                    _activeSocket = null;
                }

                if (_sasSessionAccepted)
                {
                    SetStatus(true, true, true, "connected", $"WebSocket reconnecting: {ex.Message}", _settings.ApiBaseUrl, incrementReconnect: true);
                }
                await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
                delay = TimeSpan.FromMilliseconds(Math.Min(delay.TotalMilliseconds * 2, 15000));
            }
            finally
            {
                socket?.Dispose();
            }
        }
    }

    private void HandleWebSocketMessage(string text)
    {
        JsonObject? data;
        try
        {
            data = JsonNode.Parse(text) as JsonObject;
        }
        catch
        {
            return;
        }

        if (data is null)
        {
            return;
        }

        TryRaiseUnlockFromJson(data);
    }

    private void OnPreviewFrameAvailable(byte[] jpeg)
    {
        var capturedAt = DateTimeOffset.Now;
        RecognitionStatus status;
        lock (_gate)
        {
            _status = _status with
            {
                StreamHealthy = true,
                ConnectionState = "live",
                LastError = "",
                LastFrameAt = capturedAt
            };
            status = _status;
        }

        StatusChanged?.Invoke(this, status);
        PreviewFrameAvailable?.Invoke(this, new PreviewFrame(jpeg, capturedAt));
    }

    private void TryRaiseUnlockFromJson(JsonObject data)
    {
        var type = ReadStringDeep(data, "type", "event", "status", "state");
        var confidence = ReadDoubleDeep(data, "confidence", "score", "similarity", "match_score");
        var normalizedConfidence = confidence <= 1 ? confidence * 100 : confidence;
        var employeeId = ReadStringDeep(data, "employee_id", "employeeId", "user_id", "userid", "ntid", "id").ToUpperInvariant();
        var name = ReadStringDeep(data, "display_name", "displayName", "name", "user_name", "username", "recognized_name", "matched_name");
        var unlock = type.Contains("unlock", StringComparison.OrdinalIgnoreCase)
            || type.Contains("authorized", StringComparison.OrdinalIgnoreCase)
            || type.Contains("recognized", StringComparison.OrdinalIgnoreCase)
            || type.Contains("matched", StringComparison.OrdinalIgnoreCase)
            || ReadBoolDeep(data, "authorized", "recognized", "matched", "success", "unlock", "unlocked")
            || (normalizedConfidence >= 65 && (!string.IsNullOrWhiteSpace(employeeId) || !string.IsNullOrWhiteSpace(name)));
        if (!unlock)
        {
            return;
        }

        var eventId = ReadStringDeep(data, "event_id", "eventId", "match_id", "matchId");
        if (string.IsNullOrWhiteSpace(eventId))
        {
            eventId = $"{employeeId}|{name}|{ReadStringDeep(data, "timestamp", "time", "last_seen", "updated_at")}";
        }

        if (string.IsNullOrWhiteSpace(eventId))
        {
            eventId = $"{employeeId}|{name}|{DateTimeOffset.Now:yyyyMMddHHmmss}";
        }

        if (!_seenUnlockEvents.TryAdd(eventId, 0))
        {
            return;
        }

        UnlockRecognized?.Invoke(this, new RecognitionUnlockEvent(
            string.IsNullOrWhiteSpace(name) ? employeeId : name,
            string.IsNullOrWhiteSpace(employeeId) ? "PI" : employeeId,
            normalizedConfidence,
            eventId,
            DateTimeOffset.Now));
    }

    private Task SendWsSessionNoticeAsync(string type, string reason)
    {
        return SendWsSessionNoticeAsync(type, reason, _runCts?.Token ?? CancellationToken.None);
    }

    private Task SendWsSessionNoticeAsync(string type, string reason, CancellationToken cancellationToken)
    {
        var socket = _activeSocket;
        if (socket is null || socket.State != WebSocketState.Open || string.IsNullOrWhiteSpace(_lockSessionId))
        {
            return Task.CompletedTask;
        }

        return PiWebSocketClient.SendAsync(socket, new JsonObject
        {
            ["type"] = type,
            ["lock_session_id"] = _lockSessionId,
            ["reason"] = reason,
            ["client_id"] = _settings.ClientId,
            ["client_time"] = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss")
        }, cancellationToken);
    }

    private async Task RefreshUsersFromPiAsync(CancellationToken cancellationToken)
    {
        var data = await RequestAsync("GET", "/users", timeoutSeconds: 15, cancellationToken: cancellationToken).ConfigureAwait(false);
        var usersNode = data["users"] as JsonArray ?? data["items"] as JsonArray ?? [];
        var users = new List<FaceUserRecord>();
        foreach (var node in usersNode)
        {
            if (node is not JsonObject user)
            {
                continue;
            }

            var employeeId = ReadString(user, "employee_id", "user_id", "id", "ntid").ToUpperInvariant();
            var name = ReadString(user, "display_name", "name", "user_name");
            if (string.IsNullOrWhiteSpace(employeeId) && string.IsNullOrWhiteSpace(name))
            {
                continue;
            }

            users.Add(new FaceUserRecord
            {
                UserId = string.IsNullOrWhiteSpace(employeeId) ? Guid.NewGuid().ToString("N") : employeeId,
                EmployeeId = employeeId,
                DisplayName = string.IsNullOrWhiteSpace(name) ? employeeId : name,
                SampleCount = Math.Max(0, ReadInt(user, "photos", "photo_count", "sample_count", "samples"))
            });
        }

        lock (_gate)
        {
            _users = users.OrderBy(u => u.EmployeeId).ToList();
        }
    }

    private async Task<JsonObject> RequestAsync(string method, string endpoint, JsonObject? payload = null, int timeoutSeconds = 15, CancellationToken cancellationToken = default)
    {
        return await _api.RequestAsync(method, endpoint, payload, timeoutSeconds, cancellationToken).ConfigureAwait(false);
    }

    private async Task TryPostAsync(string endpoint, int timeoutSeconds, CancellationToken cancellationToken)
    {
        try
        {
            await RequestAsync("POST", endpoint, timeoutSeconds: timeoutSeconds, cancellationToken: cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            _log.Write($"{endpoint} warning: {ex.Message}");
        }
    }

    private Task SasConnectAsync(bool force, CancellationToken cancellationToken)
    {
        return RequestAsync("POST", "/sas/connect", new JsonObject
        {
            ["client_id"] = _settings.ClientId,
            ["client_name"] = _settings.ClientName,
            ["client_user"] = Environment.UserName,
            ["client_host"] = Environment.MachineName,
            ["force"] = force
        }, timeoutSeconds: 8, cancellationToken: cancellationToken);
    }

    private async Task EnsureSasSessionAcceptedAsync(CancellationToken cancellationToken)
    {
        if (_sasSessionAccepted)
        {
            return;
        }

        await SasConnectAsync(force: false, cancellationToken).ConfigureAwait(false);
        await RequestAsync("POST", "/start-recognition", timeoutSeconds: 20, cancellationToken: cancellationToken).ConfigureAwait(false);
        await RefreshUsersFromPiAsync(cancellationToken).ConfigureAwait(false);
        _sasSessionAccepted = true;
    }

    private async Task<(string Username, string Password)> GetPiSftpCredentialsAsync(CancellationToken cancellationToken)
    {
        var status = await RequestAsync("GET", "/status", timeoutSeconds: 8, cancellationToken: cancellationToken).ConfigureAwait(false);
        var username = ReadString(status, "system_user", "ssh_username");
        if (string.IsNullOrWhiteSpace(username))
        {
            username = "jbl_facerec";
        }

        return (username, username);
    }

    private Task SasDisconnectAsync(bool force, CancellationToken cancellationToken)
    {
        return RequestAsync("POST", "/sas/disconnect", new JsonObject
        {
            ["client_id"] = _settings.ClientId,
            ["force"] = force
        }, timeoutSeconds: 8, cancellationToken: cancellationToken);
    }

    private void EnsureClientId()
    {
        if (!string.IsNullOrWhiteSpace(_settings.ClientId))
        {
            return;
        }

        var root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SAS");
        Directory.CreateDirectory(root);
        var path = Path.Combine(root, "sas_client_id.txt");
        if (File.Exists(path))
        {
            _settings.ClientId = File.ReadAllText(path).Trim();
        }

        if (string.IsNullOrWhiteSpace(_settings.ClientId))
        {
            _settings.ClientId = $"{Environment.MachineName}-{Guid.NewGuid():N}";
            File.WriteAllText(path, _settings.ClientId);
        }
    }

    private void SetStatus(bool isRunning, bool healthy, bool modelReady, string state, string error, string url, bool incrementReconnect = false)
    {
        RecognitionStatus status;
        lock (_gate)
        {
            var hasRecentFrame = _status.LastFrameAt is not null &&
                DateTimeOffset.Now - _status.LastFrameAt.Value < TimeSpan.FromSeconds(10);
            if (!healthy && hasRecentFrame && state.Contains("websocket", StringComparison.OrdinalIgnoreCase))
            {
                healthy = true;
                state = "live";
                error = "";
            }

            var disconnected = state.Contains("disconnect", StringComparison.OrdinalIgnoreCase);
            var lastFrameAt = !isRunning || disconnected ? null : _status.LastFrameAt;
            _status = _status with
            {
                IsRunning = isRunning,
                StreamHealthy = healthy,
                ModelReady = modelReady,
                ConnectionState = state,
                LastError = error,
                RtspUrl = url,
                ReconnectCount = _status.ReconnectCount + (incrementReconnect ? 1 : 0),
                LastFrameAt = lastFrameAt
            };
            status = _status;
        }

        StatusChanged?.Invoke(this, status);
    }

    private static async Task WaitQuietlyAsync(Task? task, CancellationToken cancellationToken)
    {
        if (task is null)
        {
            return;
        }

        try
        {
            await task.WaitAsync(TimeSpan.FromSeconds(2), cancellationToken).ConfigureAwait(false);
        }
        catch
        {
        }
    }

    private static FaceUserRecord CloneUser(FaceUserRecord user)
    {
        return new FaceUserRecord
        {
            UserId = user.UserId,
            DisplayName = user.DisplayName,
            EmployeeId = user.EmployeeId,
            CreatedAt = user.CreatedAt,
            SampleCount = user.SampleCount,
            Embeddings = user.Embeddings.Select(e => e.ToArray()).ToList()
        };
    }

    private static string ReadString(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is not null)
            {
                if (node is JsonValue value && value.TryGetValue<string>(out var s))
                {
                    return s ?? "";
                }

                return node.ToJsonString();
            }
        }

        return "";
    }

    private static int ReadInt(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is not null)
            {
                if (node is JsonValue value)
                {
                    if (value.TryGetValue<int>(out var i)) return i;
                    if (value.TryGetValue<long>(out var l)) return (int)l;
                    if (value.TryGetValue<string>(out var s) && int.TryParse(s, out var parsed)) return parsed;
                }
            }
        }

        return 0;
    }

    private static double ReadDouble(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is JsonValue value)
            {
                if (value.TryGetValue<double>(out var d)) return d;
                if (value.TryGetValue<string>(out var s) && double.TryParse(s, out var parsed)) return parsed;
            }
        }

        return 0;
    }

    private static string ReadStringDeep(JsonObject data, params string[] keys)
    {
        return ReadDeep(data, keys, node =>
        {
            if (node is JsonValue value && value.TryGetValue<string>(out var s))
            {
                return s ?? "";
            }

            return node is null ? "" : node.ToJsonString();
        }) ?? "";
    }

    private static double ReadDoubleDeep(JsonObject data, params string[] keys)
    {
        return ReadDeep(data, keys, node =>
        {
            if (node is JsonValue value)
            {
                if (value.TryGetValue<double>(out var d)) return d;
                if (value.TryGetValue<string>(out var s) && double.TryParse(s, out var parsed)) return parsed;
            }

            return 0d;
        });
    }

    private static bool ReadBoolDeep(JsonObject data, params string[] keys)
    {
        return ReadDeep(data, keys, node =>
        {
            if (node is JsonValue value)
            {
                if (value.TryGetValue<bool>(out var b)) return b;
                if (value.TryGetValue<string>(out var s))
                {
                    if (bool.TryParse(s, out var parsed)) return parsed;
                    return s.Equals("1", StringComparison.OrdinalIgnoreCase)
                        || s.Equals("yes", StringComparison.OrdinalIgnoreCase)
                        || s.Equals("true", StringComparison.OrdinalIgnoreCase)
                        || s.Equals("recognized", StringComparison.OrdinalIgnoreCase)
                        || s.Equals("matched", StringComparison.OrdinalIgnoreCase)
                        || s.Equals("authorized", StringComparison.OrdinalIgnoreCase);
                }

                if (value.TryGetValue<int>(out var i)) return i != 0;
            }

            return false;
        });
    }

    private static T? ReadDeep<T>(JsonNode? node, IReadOnlyCollection<string> keys, Func<JsonNode, T> convert)
    {
        if (node is JsonObject obj)
        {
            foreach (var item in obj)
            {
                if (item.Value is not null && keys.Any(key => string.Equals(key, item.Key, StringComparison.OrdinalIgnoreCase)))
                {
                    var value = convert(item.Value);
                    if (value is not null && !EqualityComparer<T>.Default.Equals(value, default))
                    {
                        return value;
                    }
                }
            }

            foreach (var item in obj)
            {
                var value = ReadDeep(item.Value, keys, convert);
                if (value is not null && !EqualityComparer<T>.Default.Equals(value, default))
                {
                    return value;
                }
            }
        }
        else if (node is JsonArray array)
        {
            foreach (var item in array)
            {
                var value = ReadDeep(item, keys, convert);
                if (value is not null && !EqualityComparer<T>.Default.Equals(value, default))
                {
                    return value;
                }
            }
        }

        return default;
    }

    private static bool ReadBool(JsonObject data, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (data.TryGetPropertyValue(key, out var node) && node is JsonValue value)
            {
                if (value.TryGetValue<bool>(out var b)) return b;
                if (value.TryGetValue<string>(out var s) && bool.TryParse(s, out var parsed)) return parsed;
            }
        }

        return false;
    }

    public void Dispose()
    {
        _runCts?.Cancel();
        _runCts?.Dispose();
        _api.Dispose();
        _previewStream.Dispose();
    }
}
