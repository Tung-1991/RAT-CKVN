param([ValidateSet('Start', 'Backend', 'Demo', 'Install', 'Check')][string]$Action = 'Start')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path
Set-Location -LiteralPath $projectRoot
function Get-ProjectPython {
    foreach ($relativePath in @('.venv\Scripts\python.exe')) {
        $candidatePath = Join-Path $projectRoot $relativePath
        if (Test-Path -LiteralPath $candidatePath -PathType Leaf) { return $candidatePath }
    }
    throw 'Chua co moi truong. Chon muc 4 trong START_SYSTEM.bat.'
}
try {
    if ($Action -eq 'Install') {
        $newPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $newPython -PathType Leaf)) {
            & py -3 -m venv (Join-Path $projectRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Can Python 3.11 tro len co Tkinter.' }
        }
        & $newPython -m pip install -r (Join-Path $projectRoot 'requirements-dev.txt')
        exit $LASTEXITCODE
    }
    $projectPython = Get-ProjectPython
    if ($Action -eq 'Check') {
        & $projectPython -X utf8 -m pytest (Join-Path $projectRoot 'support\tests') -q -p no:cacheprovider --tb=short
    } elseif ($Action -eq 'Backend') {
        & $projectPython -X utf8 -m ckps.signal_app
    } elseif ($Action -eq 'Demo') {
        & $projectPython -X utf8 -m ckps --demo
    } else {
        & $projectPython -X utf8 -m ckps
    }
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
