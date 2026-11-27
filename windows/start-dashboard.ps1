<#
.SYNOPSIS
Start the AlgoRE Next.js dashboard on Windows 11.
.PARAMETER Build
Build and serve the production output instead of the dev server.
#>
[CmdletBinding()]
param([switch]$Build)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dashboard = Join-Path $root 'dashboard'
$envPath = Join-Path $root '.env'

if (Test-Path $envPath) {
    foreach ($line in [System.IO.File]::ReadAllLines($envPath)) {
        if ($line -match '^\s*#') { continue }
        $at = $line.IndexOf('=')
        if ($at -lt 1) { continue }
        $key = $line.Substring(0, $at).Trim()
        $value = $line.Substring($at + 1).Trim()
        if ($key -and $key -notlike 'ALGORE_*' -and $key -ne 'ALLOWED_ORIGINS') {
            Set-Item -Path "env:$key" -Value $value
        }
    }
}

# Public defaults only. Never bake a key into the browser bundle.
if (-not $env:NEXT_PUBLIC_API_URL) { $env:NEXT_PUBLIC_API_URL = 'http://localhost:8000' }
if (-not $env:NEXT_PUBLIC_WS_URL) { $env:NEXT_PUBLIC_WS_URL = 'ws://localhost:8000/ws/live' }

$runDir = Join-Path $PSScriptRoot 'run'
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$pidFile = Join-Path $runDir 'dashboard.pid'
$npm = (Get-Command npm).Source

Push-Location $dashboard
try {
    if ($Build) {
        Write-Host 'Building production dashboard...' -ForegroundColor Cyan
        $env:NODE_OPTIONS = '--max-old-space-size=2048'
        & $npm run build
        if ($LASTEXITCODE -ne 0) { throw 'Dashboard build failed.' }
        $arguments = @('run', 'start')
    } else {
        $arguments = @('run', 'dev')
    }
    $child = Start-Process -FilePath $npm -ArgumentList $arguments `
        -WorkingDirectory $dashboard -NoNewWindow -PassThru
    $child.Id | Set-Content -LiteralPath $pidFile
    Write-Host 'Dashboard: http://localhost:3000 (Ctrl+C to stop)' -ForegroundColor Cyan
    $child.WaitForExit()
} finally { Pop-Location }
