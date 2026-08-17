namespace SAS.Models;

public sealed class AppSettings
{
    public string CameraHost { get; set; } = "";
    public int ApiPort { get; set; } = 5000;
    public string ClientId { get; set; } = "";
    public string ClientName { get; set; } = "Windows SAS";
    public string ServerUsername { get; set; } = "";
    public string ServerPassword { get; set; } = "";
    public string ServerPath { get; set; } = "";
    public string ServerCredentialOwnerNtid { get; set; } = "";
    public string CameraSource { get; set; } = "pi";
    public int WebcamIndex { get; set; }
    public string RtspUser { get; set; } = "admin";
    public string RtspPassword { get; set; } = "penAteam";
    public int RtspPort { get; set; } = 8554;
    public string RtspPath { get; set; } = "jabileye-stream";
    public string Transport { get; set; } = "tcp";
    public int CameraRotation { get; set; }
    public bool AutoCapture { get; set; }
    public int LockTimeoutSeconds { get; set; } = 300;
    public bool DisableKeyboardWhenLocked { get; set; }
    public bool DisableMouseWhenLocked { get; set; }
    public bool DisableUsbWhenLocked { get; set; }
    public bool EnableEmergencyHotkey { get; set; } = true;

    public string RtspUrl
    {
        get
        {
            var host = CleanHost(CameraHost);
            if (string.IsNullOrWhiteSpace(host))
            {
                return "";
            }

            return $"rtsp://{RtspUser}:{RtspPassword}@{host}:{RtspPort}/{RtspPath.TrimStart('/')}";
        }
    }

    public static string CleanHost(string? host)
    {
        var value = (host ?? "").Trim();
        foreach (var prefix in new[] { "http://", "https://", "ws://", "wss://", "rtsp://" })
        {
            if (value.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                value = value[prefix.Length..];
                break;
            }
        }

        value = value.Split('/')[0];
        var colonIndex = value.IndexOf(':');
        if (colonIndex > -1)
        {
            value = value[..colonIndex];
        }

        return value.Trim();
    }

    public string PiHost => CleanHost(CameraHost);

    public string ApiBaseUrl
    {
        get
        {
            var host = PiHost;
            if (string.IsNullOrWhiteSpace(host))
            {
                return "";
            }

            return $"http://{host}:{Math.Clamp(ApiPort, 1, 65535)}";
        }
    }

    public AppSettings Clone()
    {
        return new AppSettings
        {
            CameraHost = CameraHost,
            ApiPort = ApiPort,
            ClientId = ClientId,
            ClientName = ClientName,
            ServerUsername = ServerUsername,
            ServerPassword = ServerPassword,
            ServerPath = ServerPath,
            ServerCredentialOwnerNtid = ServerCredentialOwnerNtid,
            CameraSource = CameraSource,
            WebcamIndex = WebcamIndex,
            RtspUser = RtspUser,
            RtspPassword = RtspPassword,
            RtspPort = RtspPort,
            RtspPath = RtspPath,
            Transport = Transport,
            CameraRotation = CameraRotation,
            AutoCapture = AutoCapture,
            LockTimeoutSeconds = LockTimeoutSeconds,
            DisableKeyboardWhenLocked = DisableKeyboardWhenLocked,
            DisableMouseWhenLocked = DisableMouseWhenLocked,
            DisableUsbWhenLocked = DisableUsbWhenLocked,
            EnableEmergencyHotkey = EnableEmergencyHotkey
        };
    }
}
