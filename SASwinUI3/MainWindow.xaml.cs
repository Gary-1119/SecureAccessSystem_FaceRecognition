using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Windowing;
using System.IO;
using System.Runtime.InteropServices;
using WinRT.Interop;
using Windows.Graphics;

namespace SAS;

/// <summary>
/// The application window. This hosts the public dashboard shell on startup.
/// </summary>
public sealed partial class MainWindow : Window
{
    public static bool IsWindowMaximized { get; private set; }

    private const int MinimumWindowWidth = 1120;
    private const int MinimumWindowHeight = 720;
    private const int StartupWindowWidth = 1420;
    private const int StartupWindowHeight = 920;
    private const uint WmGetMinMaxInfo = 0x0024;
    private const uint WmSetIcon = 0x0080;
    private const int IconSmall = 0;
    private const int IconBig = 1;
    private const int IconSmall2 = 2;
    private const uint ImageIcon = 1;
    private const uint LoadFromFile = 0x00000010;
    private const int GclpHicon = -14;
    private const int GclpHiconSmall = -34;
    private const int SmCxIcon = 11;
    private const int SmCyIcon = 12;
    private const int SmCxSmallIcon = 49;
    private const int SmCySmallIcon = 50;

    private readonly SubclassProc _subclassProc;
    private bool _restoreStartupSizeOnNextRestore;
    private IntPtr _largeIconHandle;
    private IntPtr _smallIconHandle;

    public MainWindow()
    {
        InitializeComponent();
        _subclassProc = WindowSubclassProc;

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(AppTitleBar);

        AppWindow.TitleBar.PreferredHeightOption = TitleBarHeightOption.Tall;
        SetWindowIcons();
        SetTitleBarLogo();
        AppWindow.Title = "Secure Access System";
        AppWindow.Changed += AppWindow_Changed;
        SetStartupWindowSize();

        RootFrame.Navigate(typeof(MainPage));
        if (RootFrame.Content is MainPage page)
        {
            AppTitleBar.IsBackButtonEnabled = page.CanNavigateBack;
            page.BackAvailabilityChanged += (_, canGoBack) => AppTitleBar.IsBackButtonEnabled = canGoBack;
        }

        SetMinimumWindowSize();
    }

    private void SetWindowIcons()
    {
        var iconPath = ResolveAssetPath("SasLogo.ico");
        if (!File.Exists(iconPath))
        {
            return;
        }

        AppWindow.SetIcon(iconPath);

        var hwnd = WindowNative.GetWindowHandle(this);
        var largeWidth = GetSystemMetrics(SmCxIcon);
        var largeHeight = GetSystemMetrics(SmCyIcon);
        var smallWidth = GetSystemMetrics(SmCxSmallIcon);
        var smallHeight = GetSystemMetrics(SmCySmallIcon);

        _largeIconHandle = LoadImage(IntPtr.Zero, iconPath, ImageIcon, largeWidth, largeHeight, LoadFromFile);
        _smallIconHandle = LoadImage(IntPtr.Zero, iconPath, ImageIcon, smallWidth, smallHeight, LoadFromFile);

        if (_largeIconHandle != IntPtr.Zero)
        {
            SendMessage(hwnd, WmSetIcon, new IntPtr(IconBig), _largeIconHandle);
            SetClassLongPtr(hwnd, GclpHicon, _largeIconHandle);
        }

        if (_smallIconHandle != IntPtr.Zero)
        {
            SendMessage(hwnd, WmSetIcon, new IntPtr(IconSmall), _smallIconHandle);
            SendMessage(hwnd, WmSetIcon, new IntPtr(IconSmall2), _smallIconHandle);
            SetClassLongPtr(hwnd, GclpHiconSmall, _smallIconHandle);
        }
    }

    private void AppTitleBar_BackRequested(TitleBar sender, object args)
    {
        if (RootFrame.Content is MainPage page)
        {
            page.NavigateBackFromTitleBar();
        }
    }

    private void SetTitleBarLogo()
    {
        var logoPath = ResolveAssetPath("SasLogo.png");
        if (!File.Exists(logoPath))
        {
            return;
        }

        AppTitleBar.IconSource = new BitmapIconSource
        {
            UriSource = new Uri(logoPath),
            ShowAsMonochrome = false
        };
    }

    private void AppTitleBar_PaneToggleRequested(TitleBar sender, object args)
    {
        if (RootFrame.Content is MainPage page)
        {
            page.ToggleNavigationPane();
        }
    }

    private void AppWindow_Changed(AppWindow sender, AppWindowChangedEventArgs args)
    {
        if (sender.Presenter is not OverlappedPresenter presenter)
        {
            return;
        }

        if (presenter.State == OverlappedPresenterState.Maximized)
        {
            _restoreStartupSizeOnNextRestore = true;
            return;
        }

        if (_restoreStartupSizeOnNextRestore && presenter.State == OverlappedPresenterState.Restored)
        {
            _restoreStartupSizeOnNextRestore = false;
            SetStartupWindowSize();
        }
    }

    private void SetStartupWindowSize()
    {
        if (AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.Restore();
        }

        var workArea = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Nearest).WorkArea;
        var width = Math.Clamp(StartupWindowWidth, MinimumWindowWidth, Math.Max(MinimumWindowWidth, workArea.Width - 96));
        var height = Math.Clamp(StartupWindowHeight, MinimumWindowHeight, Math.Max(MinimumWindowHeight, workArea.Height - 96));
        var x = workArea.X + Math.Max(0, (workArea.Width - width) / 2);
        var y = workArea.Y + Math.Max(0, (workArea.Height - height) / 2);

        AppWindow.MoveAndResize(new RectInt32(x, y, width, height));
    }

    private void SetMinimumWindowSize()
    {
        var hwnd = WindowNative.GetWindowHandle(this);
        SetWindowSubclass(hwnd, _subclassProc, UIntPtr.Zero, UIntPtr.Zero);
    }

    private IntPtr WindowSubclassProc(IntPtr hwnd, uint message, UIntPtr wParam, IntPtr lParam, UIntPtr subclassId, UIntPtr refData)
    {
        if (message == WmGetMinMaxInfo)
        {
            var info = Marshal.PtrToStructure<MinMaxInfo>(lParam);
            info.MinTrackSize.X = MinimumWindowWidth;
            info.MinTrackSize.Y = MinimumWindowHeight;
            Marshal.StructureToPtr(info, lParam, false);
            return IntPtr.Zero;
        }

        return DefSubclassProc(hwnd, message, wParam, lParam);
    }

    private delegate IntPtr SubclassProc(IntPtr hwnd, uint message, UIntPtr wParam, IntPtr lParam, UIntPtr subclassId, UIntPtr refData);

    [DllImport("Comctl32.dll", SetLastError = true)]
    private static extern bool SetWindowSubclass(IntPtr hwnd, SubclassProc subclassProc, UIntPtr subclassId, UIntPtr refData);

    [DllImport("Comctl32.dll", SetLastError = true)]
    private static extern IntPtr DefSubclassProc(IntPtr hwnd, uint message, UIntPtr wParam, IntPtr lParam);

    [DllImport("User32.dll", SetLastError = true)]
    private static extern IntPtr SendMessage(IntPtr hwnd, uint message, IntPtr wParam, IntPtr lParam);

    [DllImport("User32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern IntPtr LoadImage(IntPtr instance, string name, uint type, int cx, int cy, uint load);

    [DllImport("User32.dll", SetLastError = true)]
    private static extern int GetSystemMetrics(int index);

    [DllImport("User32.dll", EntryPoint = "SetClassLongPtrW", SetLastError = true)]
    private static extern IntPtr SetClassLongPtr64(IntPtr hwnd, int index, IntPtr newLong);

    [DllImport("User32.dll", EntryPoint = "SetClassLongW", SetLastError = true)]
    private static extern uint SetClassLong32(IntPtr hwnd, int index, IntPtr newLong);

    private static IntPtr SetClassLongPtr(IntPtr hwnd, int index, IntPtr newLong)
    {
        return IntPtr.Size == 8
            ? SetClassLongPtr64(hwnd, index, newLong)
            : new IntPtr(unchecked((int)SetClassLong32(hwnd, index, newLong)));
    }

    private static string ResolveAssetPath(string fileName)
    {
        foreach (var path in new[]
        {
            Path.Combine(AppContext.BaseDirectory, "Assets", fileName),
            Path.Combine(AppContext.BaseDirectory, fileName),
            Path.Combine(Environment.CurrentDirectory, "Assets", fileName)
        })
        {
            if (File.Exists(path))
            {
                return path;
            }
        }

        return Path.Combine(AppContext.BaseDirectory, "Assets", fileName);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MinMaxInfo
    {
        public NativePoint Reserved;
        public NativePoint MaxSize;
        public NativePoint MaxPosition;
        public NativePoint MinTrackSize;
        public NativePoint MaxTrackSize;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct NativePoint
    {
        public int X;
        public int Y;
    }
}
