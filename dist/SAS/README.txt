# Secure Access System Deploy Folder

Run the app:

```text
Start SAS.bat
```

App files are inside:

```text
App\
```

To autostart for all Windows users:

1. Right-click `Install common startup shortcut.ps1`.
2. Run with PowerShell as administrator.

To install and autostart for the current Windows user without administrator permission:

1. Double-click `Install for this user.bat`.
2. The installer copies SAS app files to `%LocalAppData%\Programs\SASProgramData`.
3. It creates a Desktop shortcut and an HKCU Run startup entry for the current Windows user.
4. Existing shared data in `%ProgramData%\SASstream` is preserved during updates.

To check whether SAS is registered in HKCU startup:

```powershell
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" | Select-Object "Secure Access System ProgramData"
```

Expected value:

```text
"%LocalAppData%\Programs\SASProgramData\App\SAS.exe"
```

To uninstall for the current Windows user:

1. Double-click `Uninstall for this user.bat`.
2. Choose whether to keep or delete user data.

Copy this whole `SAS` folder to another PC. Keep the `App` folder and `Start SAS.bat` together.

Fresh-start/shared data is stored for all Windows users in:

```text
%ProgramData%\SASstream
```

RTSP stream password storage:

- The ProgramData version encrypts the saved RTSP password with Windows machine-scope DPAPI.
- Any Windows user on the same PC can decrypt and reuse it through SAS.
- Other PCs cannot decrypt it by copying `settings.json` alone.

On first start with no saved settings:

- First valid login becomes admin.
- User is routed to Settings.
- No Pi disconnect prompt appears until hostname is configured.
