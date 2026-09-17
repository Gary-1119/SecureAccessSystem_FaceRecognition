$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
}

$sourceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceApp = Join-Path $sourceRoot "App"
$sourceExe = Join-Path $sourceApp "SAS.exe"
$installRoot = Join-Path $env:ProgramFiles "SASProgramData"
$dataRoot = Join-Path $env:ProgramData "SASstream"
$runKey = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run"
$runName = "Secure Access System ProgramData"
$desktopShortcutPath = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Secure Access System ProgramData.lnk"
$startMenuShortcutPath = Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "Secure Access System ProgramData.lnk"

if (-not (Test-Path -LiteralPath $sourceExe -PathType Leaf)) {
    throw "SAS.exe was not found in $sourceApp. Run this installer from the published SAS folder."
}
if (Get-Process -Name "SAS" -ErrorAction SilentlyContinue) {
    throw "SAS is running. Close SAS in every signed-in session before installing."
}

Write-Host "Installing Secure Access System for all Windows users..."
Write-Host "Install path: $installRoot"
Write-Host "Shared data path: $dataRoot"

if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $installRoot -Force | Out-Null
New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
Copy-Item -LiteralPath $sourceApp -Destination (Join-Path $installRoot "App") -Recurse -Force
Copy-Item -LiteralPath (Join-Path $sourceRoot "Start SAS.bat") -Destination (Join-Path $installRoot "Start SAS.bat") -Force
if (Test-Path -LiteralPath (Join-Path $sourceRoot "README.txt")) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot "README.txt") -Destination (Join-Path $installRoot "README.txt") -Force
}

# Existing files also need access when switching from a per-user installation.
& icacls.exe $dataRoot /grant '*S-1-5-32-545:(OI)(CI)M' /T
if ($LASTEXITCODE -ne 0) {
    throw "Could not grant standard users Modify permission to $dataRoot."
}

$startupTarget = Join-Path $installRoot "App\SAS.exe"
$launcherTarget = Join-Path $installRoot "Start SAS.bat"
$icon = Join-Path $installRoot "App\Assets\SasLogo.ico"
New-Item -Path $runKey -Force | Out-Null
Set-ItemProperty -Path $runKey -Name $runName -Value "`"$startupTarget`""

$shell = New-Object -ComObject WScript.Shell
foreach ($shortcutPath in @($desktopShortcutPath, $startMenuShortcutPath)) {
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launcherTarget
    $shortcut.WorkingDirectory = $installRoot
    $shortcut.IconLocation = $icon
    $shortcut.Save()
}

Write-Host "Installed successfully for all Windows users."
Write-Host "Startup: $runKey\$runName"
Write-Host "Public Desktop: $desktopShortcutPath"
Write-Host "All Users Start Menu: $startMenuShortcutPath"
Write-Host "SAS will start when each Windows user signs in."
