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
2. The installer copies SAS app files to `%LocalAppData%\Programs\SAS`.
3. It creates shortcuts on the current user's Desktop and Startup folder.
4. Existing user data in `%LocalAppData%\SAS` is preserved during updates.

To uninstall for the current Windows user:

1. Double-click `Uninstall for this user.bat`.
2. Choose whether to keep or delete user data.

Copy this whole `SAS` folder to another PC. Keep the `App` folder and `Start SAS.bat` together.

Fresh-start/user data is stored per Windows user in:

```text
%LocalAppData%\SAS
```

On first start with no saved settings:

- First valid login becomes admin.
- User is routed to Settings.
- No Pi disconnect prompt appears until hostname is configured.
