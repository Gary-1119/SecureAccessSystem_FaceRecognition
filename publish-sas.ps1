$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$project = Join-Path $root "SASwinUI3\SAS.csproj"
$distRoot = Join-Path $root "dist"
$packageRoot = Join-Path $distRoot "SAS"
$appRoot = Join-Path $packageRoot "App"
$runtime = "win-x64"

Set-Location $root

function Invoke-Checked {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE."
    }
}

$runningSas = Get-Process -Name "SAS" -ErrorAction SilentlyContinue
if ($runningSas) {
    throw "SAS is currently running. Close SAS from the taskbar/tray before publishing, then run .\publish-sas.ps1 again."
}

Write-Host "Running automation tests before publish..."
Invoke-Checked { powershell -ExecutionPolicy Bypass -File (Join-Path $root "run-automation-tests.ps1") }

Write-Host "Preparing deploy folder..."
Remove-Item -LiteralPath $packageRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $appRoot -Force | Out-Null

Write-Host "Publishing SAS app..."
Invoke-Checked {
    dotnet publish $project `
        --configuration Release `
        --runtime $runtime `
        --self-contained true `
        --no-restore `
        -p:PublishSingleFile=false `
        -p:PublishTrimmed=false `
        -p:PublishReadyToRun=false `
        -o $appRoot
}

@'
@echo off
setlocal
cd /d "%~dp0App"
start "" "SAS.exe"
'@ | Set-Content -Path (Join-Path $packageRoot "Start SAS.bat") -Encoding ASCII

@'
$ErrorActionPreference = "Stop"
$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $packageRoot "Start SAS.bat"
$startup = [Environment]::GetFolderPath("CommonStartup")
$shortcutPath = Join-Path $startup "Secure Access System.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $packageRoot
$shortcut.IconLocation = Join-Path $packageRoot "App\Assets\SasLogo.ico"
$shortcut.Save()

Write-Host "Startup shortcut created:"
Write-Host $shortcutPath
'@ | Set-Content -Path (Join-Path $packageRoot "Install common startup shortcut.ps1") -Encoding ASCII

@'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install for this user.ps1"
pause
'@ | Set-Content -Path (Join-Path $packageRoot "Install for this user.bat") -Encoding ASCII

@'
$ErrorActionPreference = "Stop"

$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\SAS"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Secure Access System.lnk"
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopShortcutPath = Join-Path $desktop "Secure Access System.lnk"

$runningSas = Get-Process -Name "SAS" -ErrorAction SilentlyContinue
if ($runningSas) {
    throw "SAS is currently running. Close SAS from the taskbar/tray before installing."
}

Write-Host "Installing Secure Access System for current user..."
Write-Host "Source: $sourceRoot"
Write-Host "Install path: $installRoot"
Write-Host "User data path preserved: $env:LOCALAPPDATA\SAS"

if (Test-Path $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot "App") -Destination (Join-Path $installRoot "App") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot "Start SAS.bat") -Destination (Join-Path $installRoot "Start SAS.bat") -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot "README.txt") -Destination (Join-Path $installRoot "README.txt") -Force -ErrorAction SilentlyContinue

$target = Join-Path $installRoot "Start SAS.bat"
$icon = Join-Path $installRoot "App\Assets\SasLogo.ico"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $installRoot
$shortcut.IconLocation = $icon
$shortcut.Save()

$shortcut = $shell.CreateShortcut($desktopShortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $installRoot
$shortcut.IconLocation = $icon
$shortcut.Save()

Write-Host ""
Write-Host "Installed successfully."
Write-Host "Startup shortcut:"
Write-Host $shortcutPath
Write-Host "Desktop shortcut:"
Write-Host $desktopShortcutPath
Write-Host ""
Write-Host "SAS will auto-start when this Windows user signs in."
'@ | Set-Content -Path (Join-Path $packageRoot "Install for this user.ps1") -Encoding ASCII

@'
@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Uninstall for this user.ps1"
pause
'@ | Set-Content -Path (Join-Path $packageRoot "Uninstall for this user.bat") -Encoding ASCII

@'
$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "Programs\SAS"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Secure Access System.lnk"
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopShortcutPath = Join-Path $desktop "Secure Access System.lnk"

$runningSas = Get-Process -Name "SAS" -ErrorAction SilentlyContinue
if ($runningSas) {
    throw "SAS is currently running. Close SAS from the taskbar/tray before uninstalling."
}

Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcutPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $installRoot -Recurse -Force -ErrorAction SilentlyContinue

$dataRoot = Join-Path $env:LOCALAPPDATA "SAS"
Write-Host ""
Write-Host "Secure Access System app files and shortcuts removed for current user."
Write-Host ""
Write-Host "User data path:"
Write-Host $dataRoot
Write-Host ""
$answer = Read-Host "Delete user data also? This removes saved hostname, admins, settings, and logs. Type DELETE to confirm"
if ($answer -eq "DELETE") {
    Remove-Item -LiteralPath $dataRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "User data deleted."
} else {
    Write-Host "User data kept."
}
'@ | Set-Content -Path (Join-Path $packageRoot "Uninstall for this user.ps1") -Encoding ASCII

@'
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
'@ | Set-Content -Path (Join-Path $packageRoot "README.txt") -Encoding ASCII

Write-Host ""
Write-Host "Publish complete:"
Write-Host $packageRoot
