using System.Runtime.InteropServices;
using SAS.Models;
using Microsoft.UI.Dispatching;

namespace SAS.Services;

public sealed class RuntimeLockService : IDisposable
{
    private const int WhKeyboardLl = 13;
    private const int WhMouseLl = 14;
    private const int WmKeyDown = 0x0100;
    private const int WmSysKeyDown = 0x0104;
    private const int WmQuit = 0x0012;
    private const int VkControl = 0x11;
    private const int VkShift = 0x10;
    private const int VkMenu = 0x12;
    private const int VkU = 0x55;

    private readonly DispatcherQueue _dispatcherQueue;
    private readonly AppLogService _log;
    private readonly LowLevelProc _keyboardProc;
    private readonly LowLevelProc _mouseProc;
    private readonly DispatcherQueueTimer _hotkeyWatchdog;

    private IntPtr _keyboardHook;
    private IntPtr _mouseHook;
    private bool _isLocked;
    private bool _keyboardBlocked;
    private bool _mouseBlocked;
    private bool _enableEmergencyHotkey = true;
    private bool _credentialEntryMode;
    private bool _disposed;
    private long _lastEmergencyFireTicks;
    private Point _mouseAnchor;
    private Rect _credentialBounds;

    public event EventHandler? EmergencyUnlockRequested;

    public RuntimeLockService(DispatcherQueue dispatcherQueue, AppLogService log)
    {
        _dispatcherQueue = dispatcherQueue;
        _log = log;
        _keyboardProc = KeyboardHookCallback;
        _mouseProc = MouseHookCallback;

        _hotkeyWatchdog = dispatcherQueue.CreateTimer();
        _hotkeyWatchdog.Interval = TimeSpan.FromMilliseconds(50);
        _hotkeyWatchdog.Tick += (_, _) => PollEmergencyHotkey();
        _hotkeyWatchdog.Start();
    }

    public void Apply(bool isLocked, AppSettings settings)
    {
        _isLocked = isLocked;
        _enableEmergencyHotkey = settings.EnableEmergencyHotkey;

        if (_enableEmergencyHotkey || (isLocked && settings.DisableKeyboardWhenLocked))
        {
            EnsureKeyboardHook();
        }
        else
        {
            ReleaseKeyboardHook();
        }

        if (isLocked && settings.DisableKeyboardWhenLocked)
        {
            _keyboardBlocked = true;
        }
        else
        {
            _keyboardBlocked = false;
        }

        if (isLocked && settings.DisableMouseWhenLocked)
        {
            DisableMouse();
        }
        else
        {
            EnableMouse();
        }
    }

    public void BeginCredentialEntryMode(int left, int top, int right, int bottom)
    {
        _credentialEntryMode = true;
        _keyboardBlocked = false;
        _mouseBlocked = true;
        _credentialBounds = new Rect
        {
            Left = left,
            Top = top,
            Right = Math.Max(left + 1, right),
            Bottom = Math.Max(top + 1, bottom)
        };

        EnsureKeyboardHook();
        EnsureMouseHook();
        ClipToCredentialBounds();
        _log.Write("Emergency admin credential prompt input mode started.");
    }

    public void EndCredentialEntryMode(AppSettings settings)
    {
        if (!_credentialEntryMode)
        {
            return;
        }

        _credentialEntryMode = false;
        ClipCursor(IntPtr.Zero);
        _log.Write("Emergency admin credential prompt input mode ended.");
        Apply(_isLocked, settings);
    }

    private void EnsureKeyboardHook()
    {
        if (_keyboardHook != IntPtr.Zero)
        {
            return;
        }

        _keyboardHook = SetWindowsHookEx(WhKeyboardLl, _keyboardProc, IntPtr.Zero, 0);
        _log.Write(_keyboardHook == IntPtr.Zero
            ? $"Keyboard hook unavailable: Win32 error {Marshal.GetLastWin32Error()}"
            : "Keyboard hook armed.");
    }

    private void ReleaseKeyboardHook()
    {
        if (_keyboardHook == IntPtr.Zero)
        {
            return;
        }

        UnhookWindowsHookEx(_keyboardHook);
        _keyboardHook = IntPtr.Zero;
        _keyboardBlocked = false;
        _log.Write("Keyboard hook released.");
    }

    private void DisableMouse()
    {
        if (!_mouseBlocked)
        {
            _mouseBlocked = true;
            _mouseAnchor = GetCursorPosition();
            ClipToAnchor();
            _log.Write("Mouse movement and click input disabled while locked.");
        }

        if (_mouseHook == IntPtr.Zero)
        {
            EnsureMouseHook();
        }
    }

    private void EnsureMouseHook()
    {
        if (_mouseHook != IntPtr.Zero)
        {
            return;
        }

        _mouseHook = SetWindowsHookEx(WhMouseLl, _mouseProc, IntPtr.Zero, 0);
        if (_mouseHook == IntPtr.Zero)
        {
            _log.Write($"Mouse click block hook unavailable: Win32 error {Marshal.GetLastWin32Error()}");
        }
    }

    private void EnableMouse()
    {
        _mouseBlocked = false;
        ClipCursor(IntPtr.Zero);

        if (_mouseHook != IntPtr.Zero)
        {
            UnhookWindowsHookEx(_mouseHook);
            _mouseHook = IntPtr.Zero;
            _log.Write("Mouse hook released.");
        }
    }

    private IntPtr KeyboardHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0)
        {
            var message = wParam.ToInt32();
            if (message == WmKeyDown || message == WmSysKeyDown)
            {
                if (_credentialEntryMode)
                {
                    return CallNextHookEx(_keyboardHook, nCode, wParam, lParam);
                }

                if (IsEmergencyComboDown())
                {
                    FireEmergencyUnlock();
                    return IntPtr.Zero;
                }

                if (_isLocked && _keyboardBlocked)
                {
                    var key = Marshal.PtrToStructure<KeyboardHookStruct>(lParam).VkCode;
                    if (IsModifierKey(key))
                    {
                        return IntPtr.Zero;
                    }

                    return new IntPtr(1);
                }
            }
        }

        return CallNextHookEx(_keyboardHook, nCode, wParam, lParam);
    }

    private IntPtr MouseHookCallback(int nCode, IntPtr wParam, IntPtr lParam)
    {
        if (nCode >= 0 && _isLocked && _credentialEntryMode)
        {
            ClipToCredentialBounds();
            return CallNextHookEx(_mouseHook, nCode, wParam, lParam);
        }

        if (nCode >= 0 && _isLocked && _mouseBlocked)
        {
            ClipToAnchor();
            return new IntPtr(1);
        }

        return CallNextHookEx(_mouseHook, nCode, wParam, lParam);
    }

    private void PollEmergencyHotkey()
    {
        if (!_isLocked || !_enableEmergencyHotkey)
        {
            return;
        }

        if (IsEmergencyComboDown())
        {
            FireEmergencyUnlock();
        }

        if (_mouseBlocked)
        {
            if (_credentialEntryMode)
            {
                ClipToCredentialBounds();
            }
            else
            {
                ClipToAnchor();
            }
        }
    }

    private void FireEmergencyUnlock()
    {
        var now = Environment.TickCount64;
        if (now - Interlocked.Read(ref _lastEmergencyFireTicks) < 700)
        {
            return;
        }

        Interlocked.Exchange(ref _lastEmergencyFireTicks, now);
        _dispatcherQueue.TryEnqueue(() => EmergencyUnlockRequested?.Invoke(this, EventArgs.Empty));
    }

    private static bool IsEmergencyComboDown()
    {
        var ctrl = IsKeyDown(VkControl) || IsKeyDown(0xA2) || IsKeyDown(0xA3);
        var shift = IsKeyDown(VkShift) || IsKeyDown(0xA0) || IsKeyDown(0xA1);
        var alt = IsKeyDown(VkMenu) || IsKeyDown(0xA4) || IsKeyDown(0xA5);
        var u = IsKeyDown(VkU);
        return (ctrl && shift && alt) || (ctrl && alt && u);
    }

    private static bool IsModifierKey(int virtualKey)
    {
        return virtualKey is VkControl or VkShift or VkMenu or 0xA2 or 0xA3 or 0xA0 or 0xA1 or 0xA4 or 0xA5;
    }

    private static bool IsKeyDown(int virtualKey)
    {
        return (GetAsyncKeyState(virtualKey) & 0x8000) != 0;
    }

    private static Point GetCursorPosition()
    {
        return GetCursorPos(out var point) ? point : new Point();
    }

    private void ClipToAnchor()
    {
        var rect = new Rect
        {
            Left = _mouseAnchor.X,
            Top = _mouseAnchor.Y,
            Right = _mouseAnchor.X + 1,
            Bottom = _mouseAnchor.Y + 1
        };
        ClipCursor(ref rect);
        SetCursorPos(_mouseAnchor.X, _mouseAnchor.Y);
    }

    private void ClipToCredentialBounds()
    {
        var rect = _credentialBounds;
        ClipCursor(ref rect);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _hotkeyWatchdog.Stop();
        ReleaseKeyboardHook();
        EnableMouse();
    }

    private delegate IntPtr LowLevelProc(int nCode, IntPtr wParam, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    private struct Point
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Rect
    {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KeyboardHookStruct
    {
        public int VkCode;
        public int ScanCode;
        public int Flags;
        public int Time;
        public IntPtr ExtraInfo;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, LowLevelProc lpfn, IntPtr hMod, uint dwThreadId);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnhookWindowsHookEx(IntPtr hhk);

    [DllImport("user32.dll")]
    private static extern IntPtr CallNextHookEx(IntPtr hhk, int nCode, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int vKey);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out Point lpPoint);

    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    private static extern bool ClipCursor(ref Rect lpRect);

    [DllImport("user32.dll")]
    private static extern bool ClipCursor(IntPtr lpRect);

    [DllImport("user32.dll")]
    private static extern bool PostThreadMessage(uint idThread, int msg, IntPtr wParam, IntPtr lParam);
}
