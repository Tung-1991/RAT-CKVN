# Dispatch only the action explicitly selected in the menu.
function Invoke-CkpsAction {
    param([string]$ProjectRoot, [string]$Action)
    if ($Action -eq 'Update') {
        . (Join-Path $PSScriptRoot 'update.ps1')
        Update-CkpsSource -ProjectRoot $ProjectRoot
        return
    }
    . (Join-Path $PSScriptRoot 'bootstrap.ps1')
    if ($Action -in @('Install', 'Prepare')) {
        $python = Initialize-CkpsEnvironment -ProjectRoot $ProjectRoot
        & $python -m pip check | Out-Host
        if ($LASTEXITCODE -ne 0) {
            Initialize-CkpsEnvironment -ProjectRoot $ProjectRoot -Repair | Out-Null
        }
        Write-Host 'Moi truong da san sang. Chon muc 1 de mo app.' -ForegroundColor Green
        return
    }
    $python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
    if (-not (Test-CkpsPython $python -Dependencies)) {
        throw 'Moi truong chua san sang. Chon muc 3 de ra soat / cai moi truong.'
    }
    if ($Action -eq 'Check') {
        & $python -X utf8 -m pytest (Join-Path $ProjectRoot 'support\tests') -q -p no:cacheprovider --tb=short
        if ($LASTEXITCODE -ne 0) { throw 'Kiem thu that bai; xem chi tiet ben tren.' }
        return
    }
    if ($Action -notin @('Start', 'Blackbox', 'Backend')) { throw 'Lua chon khong hop le.' }
    $module = if ($Action -eq 'Start') { 'ckps' } else { 'ckps.signal_app' }
    $windowless = Join-Path $ProjectRoot '.venv\Scripts\pythonw.exe'
    if (Test-Path -LiteralPath $windowless -PathType Leaf) { $python = $windowless }
    Start-Process -FilePath $python -ArgumentList @('-X', 'utf8', '-m', $module) -WorkingDirectory $ProjectRoot -WindowStyle Hidden
}
