param([ValidateSet('Start', 'Blackbox', 'Backend', 'Install', 'Prepare', 'Check', 'Update', 'Preset')][string]$Action = 'Start')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
Set-Location -LiteralPath $projectRoot
try {
    . (Join-Path $PSScriptRoot 'system.ps1')
    Invoke-CkpsAction -ProjectRoot $projectRoot -Action $Action
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
