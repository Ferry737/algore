<#
.SYNOPSIS
Start the AlgoRE FastAPI engine with one worker and automatic restart.
#>
[CmdletBinding()]
param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root '.env'
if (-not (Test-Path $envPath)) { throw 'Run windows/setup.ps1 first to create .env.' }

foreach ($line in [System.IO.File]::ReadAllLines($envPath)) {
    if ($line -match '^\s*#') { continue }
    $at = $line.IndexOf('=')
    if ($at -lt 1) { continue }
    $key = $line.Substring(0, $at).Trim()
    $value = $line.Substring($at + 1).Trim()
    if ($key) { Set-Item -Path "env:$key" -Value $value }
}

if (-not $env:ALGORE_DB_PATH) { $env:ALGORE_DB_PATH = Join-Path $root 'data\algore.db' }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $env:ALGORE_DB_PATH) | Out-Null

$runDir = Join-Path $PSScriptRoot 'run'
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$pidFile = Join-Path $runDir 'api.pid'
$python = Join-Path $root 'engine\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Virtual environment missing. Run windows/setup.ps1.' }

Write-Host "API: http://127.0.0.1:$Port/api/v1/health (Ctrl+C to stop)" -ForegroundColor Cyan
while ($true) {
    $child = Start-Process -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'app.api:app', '--host', '127.0.0.1', '--port', "$Port", '--workers', '1') `
        -WorkingDirectory (Join-Path $root 'engine') -NoNewWindow -PassThru
    $child.Id | Set-Content -LiteralPath $pidFile
    $child.WaitForExit()
    Write-Host "API stopped; restarting in 3 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3
}
