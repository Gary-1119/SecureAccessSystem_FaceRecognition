using SAS.Models;
using SAS.Services;

namespace SAS.Controllers;

public sealed class JabilEyeConnectionController
{
    private readonly IRecognitionService _recognitionService;
    private readonly AppLogService _log;

    public JabilEyeConnectionController(IRecognitionService recognitionService, AppLogService log)
    {
        _recognitionService = recognitionService;
        _log = log;
    }

    public async Task<JabilEyeConnectionResult> ConnectAsync(
        AppSettings settings,
        Func<IJabilEyeTransferService, Task>? configureTransferAsync = null,
        Action? refreshUsers = null,
        TimeSpan? waitTimeout = null,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var currentStatus = _recognitionService.CurrentStatus;
            var alreadyRunningSameHost = currentStatus.IsRunning &&
                !string.IsNullOrWhiteSpace(settings.JabilEyeHost) &&
                currentStatus.RtspUrl.Contains(settings.JabilEyeHost, StringComparison.OrdinalIgnoreCase);

            if (currentStatus.IsRunning && (!alreadyRunningSameHost || !IsEffectivelyConnected(currentStatus)))
            {
                await _recognitionService.StopAsync(cancellationToken);
                alreadyRunningSameHost = false;
            }

            if (!alreadyRunningSameHost)
            {
                await _recognitionService.ConfigureAsync(settings, cancellationToken);
                if (_recognitionService is IJabilEyeTransferService transfer && configureTransferAsync is not null)
                {
                    await configureTransferAsync(transfer);
                }
            }
            else if (_recognitionService is IJabilEyeTransferService transfer && configureTransferAsync is not null)
            {
                await configureTransferAsync(transfer);
            }

            var connectStartedAt = DateTimeOffset.Now;
            await _recognitionService.StartAsync(cancellationToken);
            var connected = await WaitForReachableAsync(waitTimeout ?? TimeSpan.FromSeconds(8), connectStartedAt, cancellationToken);
            refreshUsers?.Invoke();

            if (connected)
            {
                _log.WriteAudit("JABILEYE CONNECTED", $"Host={settings.JabilEyeHost}");
                return JabilEyeConnectionResult.Success(settings.JabilEyeHost, _recognitionService.CurrentStatus);
            }

            var status = _recognitionService.CurrentStatus;
            var message = string.IsNullOrWhiteSpace(status.LastError)
                ? $"Could not connect to {settings.JabilEyeHost}."
                : status.LastError;
            _log.WriteAudit("JABILEYE CONNECTION FAILED", $"Host={settings.JabilEyeHost}; Error={message}");
            return JabilEyeConnectionResult.Failure(settings.JabilEyeHost, message, status);
        }
        catch (Exception ex)
        {
            _log.WriteAudit("JABILEYE CONNECTION FAILED", $"Host={settings.JabilEyeHost}; Error={ex.Message}");
            return JabilEyeConnectionResult.Failure(settings.JabilEyeHost, ex.Message, _recognitionService.CurrentStatus);
        }
    }

    public async Task RetryAsync(
        AppSettings settings,
        Func<IJabilEyeTransferService, Task>? configureTransferAsync = null,
        CancellationToken cancellationToken = default)
    {
        await ConnectAsync(settings, configureTransferAsync, waitTimeout: TimeSpan.FromSeconds(6), cancellationToken: cancellationToken);
        _log.Write("JabilEye reconnect retry requested.");
    }

    public async Task StartForLockAsync(AppSettings settings, CancellationToken cancellationToken = default)
    {
        try
        {
            _recognitionService.ResetUnlockCooldown();
            await _recognitionService.ConfigureAsync(settings, cancellationToken);
            await _recognitionService.StartAsync(cancellationToken);
        }
        catch (Exception ex)
        {
            _log.Write($"Lock recognition start failed: {ex.Message}");
        }
    }

    public async Task<bool> WaitForConnectedAsync(TimeSpan timeout, CancellationToken cancellationToken = default)
    {
        var deadline = DateTimeOffset.Now + timeout;
        while (DateTimeOffset.Now < deadline)
        {
            if (IsEffectivelyConnected(_recognitionService.CurrentStatus))
            {
                return true;
            }

            await Task.Delay(250, cancellationToken);
        }

        return IsEffectivelyConnected(_recognitionService.CurrentStatus);
    }

    public async Task<bool> WaitForReachableAsync(TimeSpan timeout, DateTimeOffset freshAfter, CancellationToken cancellationToken = default)
    {
        var deadline = DateTimeOffset.Now + timeout;
        while (DateTimeOffset.Now < deadline)
        {
            if (IsReachablyConnected(_recognitionService.CurrentStatus, freshAfter))
            {
                return true;
            }

            await Task.Delay(250, cancellationToken);
        }

        return IsReachablyConnected(_recognitionService.CurrentStatus, freshAfter);
    }

    public static string GetConnectionLabel(RecognitionStatus status)
    {
        return IsEffectivelyConnected(status) ? "Connected" : "Disconnected";
    }

    public static bool IsEffectivelyConnected(RecognitionStatus status)
    {
        var state = status.ConnectionState.Trim();
        return status.IsRunning &&
            (status.StreamHealthy ||
             state.Equals("connected", StringComparison.OrdinalIgnoreCase) ||
             state.Equals("live", StringComparison.OrdinalIgnoreCase) ||
             HasRecentPreviewFrame(status));
    }

    public static bool IsReachablyConnected(RecognitionStatus status, DateTimeOffset freshAfter)
    {
        return status.IsRunning &&
            status.StreamHealthy &&
            status.LastFrameAt is not null &&
            status.LastFrameAt.Value >= freshAfter;
    }

    public static bool HasRecentPreviewFrame(RecognitionStatus status)
    {
        return status.LastFrameAt is not null &&
            DateTimeOffset.Now - status.LastFrameAt.Value < TimeSpan.FromSeconds(60);
    }

    public static bool IsDisconnectedForPrompt(RecognitionStatus status)
    {
        if (!status.IsRunning || IsEffectivelyConnected(status))
        {
            return false;
        }

        return !string.IsNullOrWhiteSpace(status.LastError)
            || status.ConnectionState.Contains("disconnect", StringComparison.OrdinalIgnoreCase)
            || status.ConnectionState.Contains("reconnect", StringComparison.OrdinalIgnoreCase);
    }

    public static bool IsAlreadyConnectedByAnotherSas(string message)
    {
        return message.Contains("already connected", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("another SAS", StringComparison.OrdinalIgnoreCase) ||
            message.Contains("another SAS device", StringComparison.OrdinalIgnoreCase);
    }
}

public sealed record JabilEyeConnectionResult(bool Connected, string Host, string Message, RecognitionStatus Status)
{
    public static JabilEyeConnectionResult Success(string host, RecognitionStatus status)
    {
        return new JabilEyeConnectionResult(true, host, $"Connected to {host}.", status);
    }

    public static JabilEyeConnectionResult Failure(string host, string message, RecognitionStatus status)
    {
        return new JabilEyeConnectionResult(false, host, message, status);
    }
}
