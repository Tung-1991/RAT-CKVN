param([ValidateSet('Start', 'Backend', 'Install', 'Check')][string]$Action = 'Start')
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
    if ($Action -eq 'Install') {
        $newPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $newPython -PathType Leaf)) {
            $bootstrapPython = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
            $bootstrapArguments = @('-3')
            if (-not $bootstrapPython) {
                $bootstrapPython = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
                $bootstrapArguments = @()
            }
            if (-not $bootstrapPython) { throw 'Cai Python 3.11 tro len, kem Tcl/Tk va pip, roi chon muc 3.' }
            & $bootstrapPython.Source @bootstrapArguments -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
            if ($LASTEXITCODE -ne 0) { throw 'Can Python 3.11 tro len co Tkinter.' }
            & $bootstrapPython.Source @bootstrapArguments -m venv (Join-Path $projectRoot '.venv')
            if ($LASTEXITCODE -ne 0) { throw 'Can Python 3.11 tro len co Tkinter.' }
        }
        & $newPython -c 'import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
        if ($LASTEXITCODE -ne 0) { throw 'Moi truong can Python 3.11 tro len co Tkinter; tao lai .venv voi Python phu hop.' }
        & $newPython -m pip install -r (Join-Path $projectRoot 'requirements-dev.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Chua cai du thu vien. Kiem tra Internet/PyPI va chon lai muc 3.' }
        & $newPython -m pip check
        exit $LASTEXITCODE
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
