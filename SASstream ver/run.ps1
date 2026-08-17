$ErrorActionPreference = "Stop"

$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$main = Join-Path $appDir "main.py"

$candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python314\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe")
)

foreach ($python in $candidates) {
    if (Test-Path $python) {
        & $python $main
        exit $LASTEXITCODE
    }
}

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($pyLauncher) {
    & py -3 $main
    exit $LASTEXITCODE
}

$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    & python $main
    exit $LASTEXITCODE
}

throw "Python was not found. Install Python or update run.ps1 with the correct python.exe path."
