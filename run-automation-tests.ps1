$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Building SAS WinUI app..."
dotnet build .\SASwinUI3\SAS.csproj --no-restore
if ($LASTEXITCODE -ne 0) { throw "SAS build failed." }

Write-Host "Running automation tests..."
dotnet run --project .\SASwinUI3.AutomationTests\SASwinUI3.AutomationTests.csproj --no-restore
if ($LASTEXITCODE -ne 0) { throw "Automation tests failed." }

Write-Host "Automation test run complete."
