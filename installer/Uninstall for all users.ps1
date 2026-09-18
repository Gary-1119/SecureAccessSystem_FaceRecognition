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
$installedExe = Join-Path $installRoot "App\SAS.exe"

function Get-InstalledSasProcesses {
    @(Get-CimInstance Win32_Process -Filter "Name = 'SAS.exe'" | Where-Object {
        [string]::Equals($_.ExecutablePath, $installedExe, [StringComparison]::OrdinalIgnoreCase)
    })
}

# Remove startup first so a newly signed-in session cannot launch another copy.
Remove-ItemProperty -Path $runKey -Name $runName -ErrorAction SilentlyContinue
$runningSas = Get-InstalledSasProcesses
if ($runningSas.Count -gt 0) {
    Write-Host "Closing $($runningSas.Count) installed SAS instance(s) across Windows sessions..."
    foreach ($process in $runningSas) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }

    $deadline = (Get-Date).AddSeconds(15)
    while ((Get-InstalledSasProcesses).Count -gt 0 -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 250
    }
    if ((Get-InstalledSasProcesses).Count -gt 0) {
        throw "Some installed SAS instances are still running. Uninstall stopped before deleting app files."
    }
}

foreach ($shortcutPath in @($desktopShortcutPath, $startMenuShortcutPath)) {
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }
}
if (Test-Path -LiteralPath $installRoot) {
    Remove-Item -LiteralPath $installRoot -Recurse -Force
}

Write-Host "The all-users SAS installation was removed."
Write-Host "Shared data path: $dataRoot"
$answer = Read-Host "Press Enter or type KEEP to preserve shared settings, admins, logs and face data. Type DELETE to remove all shared data"
if ($answer -eq "DELETE") {
    Remove-Item -LiteralPath $dataRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Shared data deleted."
} else {
    Write-Host "Shared data kept for future updates."
}
