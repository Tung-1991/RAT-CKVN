# Source updates preserve the environment, credentials and trading ledgers.
function Assert-CkpsUpdateIdle {
    param([string]$ProjectRoot)
    $runtime = Join-Path $ProjectRoot 'runtime'
    if (-not (Test-Path -LiteralPath $runtime)) { return }
    foreach ($lock in Get-ChildItem -LiteralPath $runtime -Filter session.lock -File -Recurse) {
        try {
            $handle = [IO.File]::Open($lock.FullName, 'Open', 'ReadWrite', 'None')
            $handle.Dispose()
        } catch { throw 'Dong app va Blackbox truoc khi Update; du lieu dang duoc su dung.' }
    }
}

function Get-CkpsUpdateTarget {
    param([string]$ProjectRoot, [string]$Relative)
    if ($Relative -match '(^|/|\\)\.\.($|/|\\)|:|^[/\\]' -or
        $Relative -notmatch '^(ckps/|support/|START_SYSTEM\.bat$|main\.py$|backend\.py$|requirements(-dev)?\.txt$|README\.md$|AGENTS\.md$|pytest\.ini$|\.gitignore$|\.env\.example$)') {
        throw "Duong dan cap nhat khong hop le: $Relative"
    }
    $target = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $Relative))
    $boundary = $ProjectRoot.TrimEnd('\') + '\'
    if (-not $target.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { throw 'Update vuot thu muc project.' }
    $item = $target
    while ($item -ne $ProjectRoot) {
        if ((Test-Path -LiteralPath $item) -and ((Get-Item -LiteralPath $item -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Khong Update qua lien ket thu muc / tep.'
        }
        $item = Split-Path -Parent $item
    }
    return $target
}

function Update-CkpsSource {
    param([string]$ProjectRoot)
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    Assert-CkpsUpdateIdle $ProjectRoot
    if (Test-Path -LiteralPath (Join-Path $ProjectRoot '.git')) {
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Can Git de Update ban clone nay.' }
        $branch = & git -C $ProjectRoot symbolic-ref --short HEAD
        if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') { throw 'Update chi ap dung nhanh main.' }
        $changes = & git -C $ProjectRoot status --porcelain --untracked-files=no
        if ($LASTEXITCODE -ne 0 -or $changes) { throw 'Ma nguon dang sua; giu nguyen, khong ghi de hoac reset.' }
        & git -C $ProjectRoot fetch origin main
        if ($LASTEXITCODE -ne 0) { throw 'Chua tai duoc ban moi; ma nguon duoc giu nguyen.' }
        & git -C $ProjectRoot merge --ff-only origin/main
        if ($LASTEXITCODE -ne 0) { throw 'Khong the fast-forward; giu lich su, khong reset.' }
    } else {
        $work = Join-Path $ProjectRoot ('.artifacts\update-' + [Guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $work -Force | Out-Null
        $archive = Join-Path $work 'source.zip'
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/Tung-1991/RAT-CKVN/archive/refs/heads/main.zip' -OutFile $archive -TimeoutSec 180
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [IO.Compression.ZipFile]::OpenRead($archive)
        $files = @()
        try {
            foreach ($entry in $zip.Entries) {
                if ($entry.FullName.EndsWith('/')) { continue }
                if (-not $entry.FullName.StartsWith('RAT-CKVN-main/', [StringComparison]::Ordinal)) { throw 'Goi Update sai project.' }
                $relative = $entry.FullName.Substring('RAT-CKVN-main/'.Length)
                $target = Get-CkpsUpdateTarget $ProjectRoot $relative
                $staged = Join-Path $work ('source\' + $relative)
                New-Item -ItemType Directory -Path (Split-Path -Parent $staged) -Force | Out-Null
                [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $staged)
                $files += [PSCustomObject]@{ Relative=$relative; Target=$target; Staged=$staged }
            }
        } finally { $zip.Dispose() }
        foreach ($required in @('START_SYSTEM.bat', 'ckps/__main__.py', 'requirements.txt')) {
            if ($required -notin $files.Relative) { throw 'Goi Update thieu tep bat buoc; chua thay ma nguon.' }
        }
        # Download and validate everything before touching the installed source.
        Assert-CkpsUpdateIdle $ProjectRoot
        foreach ($file in $files) {
            if (Test-Path -LiteralPath $file.Target -PathType Leaf) {
                $backup = Join-Path $work ('backup\' + $file.Relative)
                New-Item -ItemType Directory -Path (Split-Path -Parent $backup) -Force | Out-Null
                Copy-Item -LiteralPath $file.Target -Destination $backup
            }
        }
        $applied = @()
        try {
            foreach ($file in $files) {
                $applied += $file
                New-Item -ItemType Directory -Path (Split-Path -Parent $file.Target) -Force | Out-Null
                Copy-Item -LiteralPath $file.Staged -Destination $file.Target -Force
            }
        } catch {
            foreach ($file in $applied) {
                $backup = Join-Path $work ('backup\' + $file.Relative)
                if (Test-Path -LiteralPath $backup) { Copy-Item -LiteralPath $backup -Destination $file.Target -Force }
                elseif (Test-Path -LiteralPath $file.Target -PathType Leaf) { Remove-Item -LiteralPath $file.Target }
            }
            throw
        }
        Write-Host 'Ban sao ma cu nam trong .artifacts/update-*/backup.'
    }
    Write-Host 'Da Update ma nguon. Chon muc 3 de ra soat moi truong, sau do muc 1 de mo app.' -ForegroundColor Green
}
