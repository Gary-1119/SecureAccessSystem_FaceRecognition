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
