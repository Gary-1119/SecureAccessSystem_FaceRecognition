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
