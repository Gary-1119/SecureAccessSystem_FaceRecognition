using System.Runtime.InteropServices;

namespace SAS.Services;

public sealed class InactivityService
{
    private long _activityResetTick = Environment.TickCount64;

    public void Reset()
    {
        _activityResetTick = Environment.TickCount64;
    }

    public int GetRemainingSeconds(int timeoutSeconds)
    {
        timeoutSeconds = Math.Max(1, timeoutSeconds);
        var idleSeconds = GetEffectiveIdleSeconds();
        return Math.Max(0, timeoutSeconds - idleSeconds);
    }

    private int GetEffectiveIdleSeconds()
    {
        var systemIdleMilliseconds = GetSystemIdleMilliseconds();
        var resetIdleMilliseconds = Math.Max(0, Environment.TickCount64 - _activityResetTick);
        return (int)(Math.Min(systemIdleMilliseconds, resetIdleMilliseconds) / 1000);
    }

    private static long GetSystemIdleMilliseconds()
    {
        var info = new LastInputInfo
        {
            CbSize = (uint)Marshal.SizeOf<LastInputInfo>()
        };

        if (!GetLastInputInfo(ref info))
        {
            return 0;
        }

        var elapsed = unchecked((uint)Environment.TickCount - info.DwTime);
        return elapsed;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct LastInputInfo
    {
        public uint CbSize;
        public uint DwTime;
    }

    [DllImport("user32.dll")]
    private static extern bool GetLastInputInfo(ref LastInputInfo plii);
}
