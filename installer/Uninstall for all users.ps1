$ErrorActionPreference = "Stop"

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs -Wait -PassThru
    exit $process.ExitCode
}

$installRoot = Join-Path $env:ProgramFiles "SASProgramData"
$dataRoot = Join-Path $env:ProgramData "SASstream"
$runKey = "HKLM:\Software\Microsoft\Windows\CurrentVersion\Run"
$runName = "Secure Access System ProgramData"
$desktopShortcutPath = Join-Path ([Environment]::GetFolderPath("CommonDesktopDirectory")) "Secure Access System ProgramData.lnk"
$startMenuShortcutPath = Join-Path ([Environment]::GetFolderPath("CommonPrograms")) "Secure Access System ProgramData.lnk"

if (Get-Process -Name "SAS" -ErrorAction SilentlyContinue) {
    throw "SAS is running. Close SAS in every signed-in session before uninstalling."
}

Remove-ItemProperty -Path $runKey -Name $runName -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $desktopShortcutPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $startMenuShortcutPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $installRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "The all-users SAS installation was removed."
Write-Host "Shared data path: $dataRoot"
$answer = Read-Host "Press Enter or type KEEP to preserve shared settings, admins, logs and face data. Type DELETE to remove all shared data"
if ($answer -eq "DELETE") {
    Remove-Item -LiteralPath $dataRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Shared data deleted."
} else {
    Write-Host "Shared data kept for future updates."
}
