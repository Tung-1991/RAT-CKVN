param([ValidateSet('Start', 'Backend', 'Install', 'Prepare', 'Check')][string]$Action = 'Start')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
Set-Location -LiteralPath $projectRoot
function Get-ProjectPython {
    foreach ($relativePath in @('.venv\Scripts\python.exe')) {
        $candidatePath = Join-Path $projectRoot $relativePath
        if (Test-Path -LiteralPath $candidatePath -PathType Leaf) { return $candidatePath }
    }
    throw 'Chua co moi truong. Chon muc 3 trong START_SYSTEM.bat.'
}
try {
    if ($Action -in @('Install', 'Prepare')) {
        . (Join-Path $PSScriptRoot 'bootstrap.ps1')
        Initialize-CkpsEnvironment -ProjectRoot $projectRoot -Repair:($Action -eq 'Install') | Out-Null
        exit 0
    }
    $projectPython = Get-ProjectPython
    if ($Action -eq 'Check') {
        & $projectPython -X utf8 -m pytest (Join-Path $projectRoot 'support\tests') -q -p no:cacheprovider --tb=short
    } elseif ($Action -eq 'Backend') {
        & $projectPython -X utf8 -m ckps.signal_app
    } else {
        & $projectPython -X utf8 -m ckps
    }
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
