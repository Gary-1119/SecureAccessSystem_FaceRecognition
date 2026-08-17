using SAS.Models;
using SAS.Services;

namespace SAS.Controllers;

public sealed class PiConnectionController
{
    private readonly IRecognitionService _recognitionService;
    private readonly AppLogService _log;

    public PiConnectionController(IRecognitionService recognitionService, AppLogService log)
    {
        _recognitionService = recognitionService;
        _log = log;
    }

    public async Task<PiConnectionResult> ConnectAsync(
        AppSettings settings,
        Func<IPiTransferService, Task>? configureTransferAsync = null,
        Action? refreshUsers = null,
        TimeSpan? waitTimeout = null,
        CancellationToken cancellationToken = default)
    {
        try
        {
            if (_recognitionService.CurrentStatus.IsRunning)
            {
                await _recognitionService.StopAsync(cancellationToken);
            }

            await _recognitionService.ConfigureAsync(settings, cancellationToken);
            if (_recognitionService is IPiTransferService transfer && configureTransferAsync is not null)
            {
                await configureTransferAsync(transfer);
            }

            await _recognitionService.StartAsync(cancellationToken);
            var connected = await WaitForConnectedAsync(waitTimeout ?? TimeSpan.FromSeconds(6), cancellationToken);
            refreshUsers?.Invoke();

            if (connected)
            {
                _log.WriteAudit("PI CONNECTED", $"Host={settings.PiHost}");
                return PiConnectionResult.Success(settings.PiHost, _recognitionService.CurrentStatus);
            }

            var status = _recognitionService.CurrentStatus;
            var message = string.IsNullOrWhiteSpace(status.LastError)
                ? $"Could not connect to {settings.PiHost}."
                : status.LastError;
            _log.WriteAudit("PI CONNECTION FAILED", $"Host={settings.PiHost}; Error={message}");
            return PiConnectionResult.Failure(settings.PiHost, message, status);
        }
        catch (Exception ex)
        {
            _log.WriteAudit("PI CONNECTION FAILED", $"Host={settings.PiHost}; Error={ex.Message}");
            return PiConnectionResult.Failure(settings.PiHost, ex.Message, _recognitionService.CurrentStatus);
        }
    }

    public async Task RetryAsync(
        AppSettings settings,
        Func<IPiTransferService, Task>? configureTransferAsync = null,
        CancellationToken cancellationToken = default)
    {
        await _recognitionService.StopAsync(cancellationToken);
        await ConnectAsync(settings, configureTransferAsync, waitTimeout: TimeSpan.FromSeconds(6), cancellationToken: cancellationToken);
        _log.Write("Pi reconnect retry requested.");
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

    public static string GetConnectionLabel(RecognitionStatus status)
    {
        return IsEffectivelyConnected(status) ? "Connected" : "Disconnected";
    }

    public static bool IsEffectivelyConnected(RecognitionStatus status)
    {
        var state = status.ConnectionState.Trim();
        var hasRecentFrame = HasRecentPreviewFrame(status);
        var hasNeverReceivedFrame = status.LastFrameAt is null;
        return status.IsRunning &&
            ((status.StreamHealthy && (hasRecentFrame || hasNeverReceivedFrame)) ||
             state.Equals("connected", StringComparison.OrdinalIgnoreCase) ||
             state.Equals("live", StringComparison.OrdinalIgnoreCase) ||
             hasRecentFrame);
    }

    public static bool HasRecentPreviewFrame(RecognitionStatus status)
    {
        return status.LastFrameAt is not null &&
            DateTimeOffset.Now - status.LastFrameAt.Value < TimeSpan.FromSeconds(10);
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

public sealed record PiConnectionResult(bool Connected, string Host, string Message, RecognitionStatus Status)
{
    public static PiConnectionResult Success(string host, RecognitionStatus status)
    {
        return new PiConnectionResult(true, host, $"Connected to {host}.", status);
    }

    public static PiConnectionResult Failure(string host, string message, RecognitionStatus status)
    {
        return new PiConnectionResult(false, host, message, status);
    }
}
