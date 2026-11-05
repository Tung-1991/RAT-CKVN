"""Installer failures stop before launch; unit scenarios never download or install."""
from pathlib import Path
import subprocess
import sys

import pytest


BOOTSTRAP = Path(__file__).resolve().parents[1] / 'bootstrap.ps1'


def quoted(value):
    return "'" + str(value).replace("'", "''") + "'"


@pytest.fixture
def setup_probe(tmp_path):
    root = tmp_path / 'project with spaces'
    root.mkdir()
    (root / 'requirements.txt').write_text('requests>=2\n')
    (root / 'requirements-dev.txt').write_text('-r requirements.txt\npytest>=8\n')

    def run(body):
        source = rf"""
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1')
Import-Module (Join-Path $PSHOME 'Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1')
. {quoted(BOOTSTRAP)}
$root = {quoted(root)}
function Invoke-WebRequest {{ throw 'Network forbidden in installer unit tests' }}
function Expand-Archive {{ throw 'Archive expansion must be explicitly mocked' }}
function Start-Process {{ throw 'External installers forbidden in unit tests' }}
{body}
exit 0
"""
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-Command', source],
                                capture_output=True, text=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout
    return root, run


def test_ready_environment_is_reused_without_network_or_package_changes(setup_probe):
    _, run = setup_probe
    run(r"""
New-Item -ItemType Directory -Path (Join-Path $root '.venv') | Out-Null
Set-Content -LiteralPath (Join-Path $root '.venv\.ckps-ready') -Value (Get-CkpsDependencyStamp $root)
function Test-CkpsPython { return $true }
function Get-CkpsPortablePython { throw 'Must not download' }
function Invoke-CkpsSetupPython { throw 'Must not reinstall' }
$result = Initialize-CkpsEnvironment $root
if ($result -ne (Join-Path $root '.venv\Scripts\python.exe')) { throw 'Wrong interpreter' }
""")


@pytest.mark.parametrize('existing_python', [False, True])
def test_fresh_or_unstamped_setup_finishes_all_steps_before_marking_ready(setup_probe, existing_python):
    _, run = setup_probe
    preparation = "New-Item -ItemType Directory -Path (Join-Path $root '.venv\\Scripts') -Force | Out-Null; Set-Content -LiteralPath (Join-Path $root '.venv\\Scripts\\python.exe') -Value 'fake'" if existing_python else ''
    expected = 'Cai thu vien,Kiem tra thu vien' if existing_python else 'Tao moi truong,Cai thu vien,Kiem tra thu vien'
    run(preparation + r"""
$script:steps = @()
function Test-CkpsPython { param($Python, [switch]$Dependencies); return (Test-Path -LiteralPath $Python) }
function Get-CkpsPortablePython { return (Join-Path $root 'portable-python.exe') }
function Invoke-CkpsSetupPython {
    param($Python, $Arguments, $Step)
    $script:steps += $Step
    if ($Step -eq 'Tao moi truong') {
        New-Item -ItemType Directory -Path (Join-Path $root '.venv\Scripts') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $root '.venv\Scripts\python.exe') -Value 'fake'
    }
}
Initialize-CkpsEnvironment $root | Out-Null
""" + f"if (($script:steps -join ',') -ne {quoted(expected)}) {{ throw 'Incomplete install flow' }}\n" + r"""
if ((Get-Content -LiteralPath (Join-Path $root '.venv\.ckps-ready') -Raw).Trim() -ne (Get-CkpsDependencyStamp $root)) { throw 'Missing ready stamp' }
""")


@pytest.mark.parametrize('failure_step', ['Cai thu vien', 'Kiem tra thu vien'])
@pytest.mark.parametrize('previously_ready', [False, True])
def test_failed_packages_never_mark_an_environment_ready(setup_probe, failure_step, previously_ready):
    _, run = setup_probe
    ready = "Set-Content -LiteralPath (Join-Path $root '.venv/.ckps-ready') -Value (Get-CkpsDependencyStamp $root)" if previously_ready else ''
    run("New-Item -ItemType Directory -Path (Join-Path $root '.venv') | Out-Null\n" + ready + r"""
function Test-CkpsPython { return $true }
function Invoke-CkpsSetupPython {
    param($Python, $Arguments, $Step)
""" + f"    if ($Step -eq {quoted(failure_step)}) {{ throw 'offline install failure' }}\n" + r"""
}
try { Initialize-CkpsEnvironment $root -Repair | Out-Null; throw 'Expected failure' }
catch { if ($_.Exception.Message -ne 'offline install failure') { throw } }
if (Test-Path -LiteralPath (Join-Path $root '.venv\.ckps-ready')) { throw 'Failed environment marked ready' }
""")


def test_corrupt_download_stops_before_archive_expansion_or_python_execution(setup_probe):
    _, run = setup_probe
    run(r"""
function Invoke-WebRequest { param($OutFile); Set-Content -LiteralPath $OutFile -Value 'corrupt archive' }
try { Get-CkpsPortablePython $root | Out-Null; throw 'Expected hash rejection' }
catch { if ($_.Exception.Message -notlike '*SHA256*') { throw } }
""")


@pytest.mark.parametrize('status,subject', [('NotSigned', 'CN=Python Software Foundation'), ('Valid', 'CN=Unexpected Publisher')])
def test_unsigned_or_wrong_publisher_runtime_is_never_executed(setup_probe, status, subject):
    _, run = setup_probe
    run(r"""
function Invoke-WebRequest { param($OutFile); Set-Content -LiteralPath $OutFile -Value 'test archive' }
$fake = Join-Path $root 'fake.zip'
Set-Content -LiteralPath $fake -Value 'test archive'
$script:CkpsPythonSha256 = (Get-FileHash -LiteralPath $fake -Algorithm SHA256).Hash
function Expand-Archive { param($LiteralPath, $DestinationPath); New-Item -ItemType Directory -Path $DestinationPath -Force | Out-Null; Set-Content -LiteralPath (Join-Path $DestinationPath 'python.exe') -Value 'fake' }
function Test-CkpsPython { throw 'Unverified interpreter executed' }
""" + f"function Get-AuthenticodeSignature {{ return [PSCustomObject]@{{ Status={quoted(status)}; SignerCertificate=[PSCustomObject]@{{ Subject={quoted(subject)} }} }} }}\n" + r"""
try { Get-CkpsPortablePython $root | Out-Null; throw 'Expected signature rejection' }
catch { if ($_.Exception.Message -notlike '*chu ky Python*') { throw } }
""")


def test_native_python_failure_is_not_reported_as_success(setup_probe):
    _, run = setup_probe
    run(f"""
try {{ Invoke-CkpsSetupPython -Python {quoted(sys.executable)} -Arguments @('-c', 'raise SystemExit(7)') -Step 'offline-probe'; throw 'Expected exit rejection' }}
catch {{ if ($_.Exception.Message -notlike '*offline-probe*exit 7*') {{ throw }} }}
""")


def test_broken_copied_environment_is_backed_up_before_rebuilding(setup_probe):
    _, run = setup_probe
    run(r"""
$old = Join-Path $root '.venv'
New-Item -ItemType Directory -Path (Join-Path $old 'Scripts') -Force | Out-Null
Set-Content -LiteralPath (Join-Path $old 'Scripts\python.exe') -Value 'old-runtime'
Set-Content -LiteralPath (Join-Path $old 'old-marker') -Value 'preserved'
function Test-CkpsPython {
    param($Python, [switch]$Dependencies)
    return (Test-Path -LiteralPath $Python) -and (Get-Content -LiteralPath $Python -Raw).Trim() -eq 'new-runtime'
}
function Get-CkpsPortablePython { return (Join-Path $root 'portable-python.exe') }
function Invoke-CkpsSetupPython {
    param($Python, $Arguments, $Step)
    if ($Step -eq 'Tao moi truong') {
        if (Test-Path -LiteralPath (Join-Path $root '.venv\old-marker')) { throw 'Old environment was not moved' }
        New-Item -ItemType Directory -Path (Join-Path $root '.venv\Scripts') -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $root '.venv\Scripts\python.exe') -Value 'new-runtime'
    }
}
Initialize-CkpsEnvironment $root | Out-Null
$backups = @(Get-ChildItem -LiteralPath (Join-Path $root '.artifacts\bootstrap-backup') -Directory)
if ($backups.Count -ne 1 -or -not (Test-Path -LiteralPath (Join-Path $backups[0].FullName 'old-marker'))) { throw 'Backup was not preserved' }
if (-not (Test-Path -LiteralPath (Join-Path $root '.venv\.ckps-ready'))) { throw 'New environment not ready' }
""")
