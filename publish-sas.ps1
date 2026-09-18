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
$installRoot = Join-Path $env:LOCALAPPDATA "Programs\SASProgramData"
$dataRoot = Join-Path $env:ProgramData "SASstream"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Secure Access System ProgramData.lnk"
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopShortcutPath = Join-Path $desktop "Secure Access System ProgramData.lnk"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runName = "Secure Access System ProgramData"

$runningSas = Get-Process -Name "SAS" -ErrorAction SilentlyContinue
if ($runningSas) {
    throw "SAS is currently running. Close SAS from the taskbar/tray before installing."
}

Write-Host "Installing Secure Access System for current user..."
Write-Host "Source: $sourceRoot"
Write-Host "Install path: $installRoot"
Write-Host "Shared data path preserved: $dataRoot"

if (Test-Path $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceRoot "App") -Destination (Join-Path $installRoot "App") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot "Start SAS.bat") -Destination (Join-Path $installRoot "Start SAS.bat") -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot "README.txt") -Destination (Join-Path $installRoot "README.txt") -Force -ErrorAction SilentlyContinue

$target = Join-Path $installRoot "Start SAS.bat"
$startupTarget = Join-Path $installRoot "App\SAS.exe"
$icon = Join-Path $installRoot "App\Assets\SasLogo.ico"
$shell = New-Object -ComObject WScript.Shell
Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name $runName -Value "`"$startupTarget`""

$shortcut = $shell.CreateShortcut($desktopShortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $installRoot
$shortcut.IconLocation = $icon
$shortcut.Save()

Write-Host ""
Write-Host "Installed successfully."
Write-Host "Startup registry entry:"
Write-Host "$runKey\$runName -> `"$startupTarget`""
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

$installRoot = Join-Path $env:LOCALAPPDATA "Programs\SASProgramData"
$startup = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startup "Secure Access System ProgramData.lnk"
$desktop = [Environment]::GetFolderPath("Desktop")
$desktopShortcutPath = Join-Path $desktop "Secure Access System ProgramData.lnk"
$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$runName = "Secure Access System ProgramData"

$runningSas = Get-Process -Name "SAS" -ErrorAction SilentlyContinue
if ($runningSas) {
    throw "SAS is currently running. Close SAS from the taskbar/tray before uninstalling."
}

Remove-Item -LiteralPath $shortcutPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcutPath -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path $runKey -Name $runName -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $installRoot -Recurse -Force -ErrorAction SilentlyContinue

$dataRoot = Join-Path $env:ProgramData "SASstream"
Write-Host ""
Write-Host "Secure Access System app files, shortcuts, and startup registry entry removed for current user."
Write-Host ""
Write-Host "User data path:"
Write-Host $dataRoot
Write-Host ""
$answer = Read-Host "Keep shared ProgramData? Press Enter or type KEEP to keep saved hostname, admins, settings, logs, and face data for future updates. Type DELETE only to remove shared data for all Windows users"
if ($answer -eq "DELETE") {
    Remove-Item -LiteralPath $dataRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Shared ProgramData deleted."
} else {
    Write-Host "Shared ProgramData kept for future SAS updates."
}
'@ | Set-Content -Path (Join-Path $packageRoot "Uninstall for this user.ps1") -Encoding ASCII

foreach ($scriptName in @(
    "Install for all users.bat",
    "Install for all users.ps1",
    "Uninstall for all users.bat",
    "Uninstall for all users.ps1"
)) {
    Copy-Item -LiteralPath (Join-Path $root "installer\$scriptName") -Destination (Join-Path $packageRoot $scriptName) -Force
}

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

To install and autostart for all Windows users:

1. Double-click `Install for all users.bat` and approve the administrator UAC prompt.
2. App files are copied to `%ProgramFiles%\SASProgramData`.
3. The installer adds an HKLM Run startup entry, a Public Desktop shortcut, and an All Users Start Menu shortcut.
4. Shared data in `%ProgramData%\SASstream` is preserved on updates.

To check the all-users startup entry:

```powershell
Get-ItemProperty "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run" | Select-Object "Secure Access System ProgramData"
```

To uninstall for all Windows users, double-click `Uninstall for all users.bat`, approve UAC, and choose whether to keep shared data. The uninstaller force-closes SAS from the all-users installation in every signed-in Windows session.
Use one installation mode per PC; installing both modes creates two startup entries for the same user.

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
'@ | Set-Content -Path (Join-Path $packageRoot "README.txt") -Encoding ASCII

Write-Host ""
Write-Host "Publish complete:"
Write-Host $packageRoot
