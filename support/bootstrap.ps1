# Full CPython runtime published for the official Python install manager.
# Kept private to this checkout: no admin, registry, PATH, or system install.
$script:CkpsPythonVersion = '3.14.10'
$script:CkpsPythonSha256 = 'cc28026a650970cc1570bb127312f1f9634eb67abfe157ae6ca1acbbc627d091'

function Test-CkpsPython {
    param([string]$Python, [switch]$Dependencies)
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { return $false }
    $probe = 'import sys,struct,tkinter,venv,ensurepip,pip; assert sys.version_info >= (3,11) and struct.calcsize(chr(80))==8'
    if ($Dependencies) { $probe += '; import customtkinter,requests,websocket,msgpack,tzdata,pytest; from PIL import Image' }
    try {
        & $Python -c $probe 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
}

function Get-CkpsDependencyStamp {
    param([string]$ProjectRoot)
    $production = (Get-FileHash -LiteralPath (Join-Path $ProjectRoot 'requirements.txt') -Algorithm SHA256).Hash
    $testing = (Get-FileHash -LiteralPath (Join-Path $ProjectRoot 'requirements-dev.txt') -Algorithm SHA256).Hash
    return "$production`:$testing`:$script:CkpsPythonVersion"
}

function Invoke-CkpsSetupPython {
    param([string]$Python, [string[]]$Arguments, [string]$Step)
    & $Python @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$Step that bai (exit $LASTEXITCODE). Kiem tra thong bao ben tren va chon lai muc 3." }
}

function Get-CkpsPortablePython {
    param([string]$ProjectRoot)
    $version = $script:CkpsPythonVersion
    $cache = Join-Path $ProjectRoot 'runtime\bootstrap'
    $archive = Join-Path $cache "python-$version-amd64.zip"
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $validArchive = (Test-Path -LiteralPath $archive -PathType Leaf) -and
        (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -eq $script:CkpsPythonSha256
    if (-not $validArchive) {
        Write-Host "Dang tai Python $version 64-bit tu python.org..."
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = 'SilentlyContinue'
        $download = "$archive.download"
        Invoke-WebRequest -UseBasicParsing -Uri "https://www.python.org/ftp/python/$version/python-$version-amd64.zip" -OutFile $download -TimeoutSec 180
        if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash -ne $script:CkpsPythonSha256) {
            throw 'Tep Python tai ve sai SHA256; dung cai dat. Chon lai muc 3 de thu lai.'
        }
        Move-Item -LiteralPath $download -Destination $archive -Force
    }
    $destination = Join-Path $ProjectRoot "runtime\python\$version"
    $python = Join-Path $destination 'python.exe'
    Write-Host 'Dang chuan bi Python rieng cho app...'
    Expand-Archive -LiteralPath $archive -DestinationPath $destination -Force
    $signature = Get-AuthenticodeSignature -LiteralPath $python
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch '(CN|O)=Python Software Foundation(,|$)') {
        throw 'Chua xac minh duoc chu ky Python Software Foundation; dung cai dat.'
    }
    if (-not (Test-CkpsPython $python)) { throw 'Python tai ve chua chay duoc Tkinter/pip tren Windows nay.' }
    return $python
}

function Initialize-CkpsEnvironment {
    param([string]$ProjectRoot, [switch]$Repair)
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'App can Windows 64-bit co Desktop/RDP.' }
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $environment = Join-Path $ProjectRoot '.venv'
    $python = Join-Path $environment 'Scripts\python.exe'
    $stampPath = Join-Path $environment '.ckps-ready'
    $stamp = Get-CkpsDependencyStamp $ProjectRoot
    if (-not $Repair -and (Test-Path -LiteralPath $stampPath) -and
            (Get-Content -LiteralPath $stampPath -Raw).Trim() -eq $stamp -and
            (Test-CkpsPython $python -Dependencies)) { return $python }
    if (Test-Path -LiteralPath $stampPath) { Remove-Item -LiteralPath $stampPath -Force }
    if (-not (Test-CkpsPython $python)) {
        $bootstrap = Get-CkpsPortablePython $ProjectRoot
        if (Test-Path -LiteralPath $environment) {
            $source = (Resolve-Path -LiteralPath $environment).ProviderPath
            $backup = [IO.Path]::GetFullPath((Join-Path $ProjectRoot ('.artifacts\bootstrap-backup\venv-' + [Guid]::NewGuid().ToString('N'))))
            $boundary = $ProjectRoot.TrimEnd('\') + '\'
            if (-not $source.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -or
                    -not $backup.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -or
                    ((Get-Item -LiteralPath $environment -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'Khong di chuyen moi truong nam ngoai thu muc project.'
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
            Move-Item -LiteralPath $source -Destination $backup
            Write-Host 'Da giu ban sao moi truong cu trong .artifacts/bootstrap-backup.'
        }
        Invoke-CkpsSetupPython -Python $bootstrap -Arguments @('-m', 'venv', $environment) -Step 'Tao moi truong'
    }
    Write-Host 'Dang cai / kiem tra thu vien CKPS...'
    Invoke-CkpsSetupPython -Python $python -Arguments @('-m', 'pip', 'install', '--force-reinstall', '--disable-pip-version-check', '-r', (Join-Path $ProjectRoot 'requirements-dev.txt')) -Step 'Cai thu vien'
    Invoke-CkpsSetupPython -Python $python -Arguments @('-m', 'pip', 'check') -Step 'Kiem tra thu vien'
    if (-not (Test-CkpsPython $python -Dependencies)) { throw 'Moi truong chua du thu vien. Chon lai muc 3 de sua.' }
    Set-Content -LiteralPath $stampPath -Value $stamp -Encoding Ascii
    Write-Host 'Da san sang. App van khoi dong PAPER / BOT OFF.' -ForegroundColor Green
    return $python
}
