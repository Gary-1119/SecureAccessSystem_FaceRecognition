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
