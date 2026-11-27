<#
.SYNOPSIS
Small interactive menu for the Windows 11 AlgoRE stack.
#>
[CmdletBinding()]
param()

$here = $PSScriptRoot
Write-Host ''
Write-Host '  AlgoRE for Windows 11' -ForegroundColor Cyan
Write-Host '  ---------------------'
Write-Host '  1  Setup (venv, dependencies, private .env)'
Write-Host '  2  Start API (port 8000)'
Write-Host '  3  Start dashboard (port 3000)'
Write-Host '  4  Stop both'
Write-Host '  5  Open Windows guide'
Write-Host '  0  Exit'
Write-Host ''
$choice = Read-Host 'Choose'

switch ($choice) {
    '1' { & (Join-Path $here 'setup.ps1') }
    '2' { & (Join-Path $here 'start-api.ps1') }
    '3' { & (Join-Path $here 'start-dashboard.ps1') }
    '4' { & (Join-Path $here 'stop.ps1') }
    '5' { Invoke-Item (Join-Path $here 'README.md') }
    '0' { exit 0 }
    default { Write-Host 'Unknown choice.' -ForegroundColor Yellow }
}
