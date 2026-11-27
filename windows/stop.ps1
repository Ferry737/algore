<#
.SYNOPSIS
Stop the AlgoRE API and dashboard processes recorded under windows\run.
#>
[CmdletBinding()]
param()

$runDir = Join-Path $PSScriptRoot 'run'
foreach ($name in @('api.pid', 'dashboard.pid')) {
    $file = Join-Path $runDir $name
    if (-not (Test-Path $file)) { continue }
    $id = (Get-Content -LiteralPath $file -Raw).Trim()
    if (-not $id) { continue }
    $proc = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $id -Force
        Write-Host "Stopped $name (PID $id)." -ForegroundColor Green
    } else {
        Write-Host "$name was not running." -ForegroundColor Yellow
    }
    Remove-Item -LiteralPath $file -Force
}
