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
