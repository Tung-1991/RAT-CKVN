# Update runs Git only. Environment setup and presets are separate menu actions.
function Update-CkpsSource {
    param([string]$ProjectRoot)
    & git -C $ProjectRoot pull --ff-only origin main
    if ($LASTEXITCODE -ne 0) { throw 'Git Update that bai; xem thong bao ben tren. Khong reset ma nguon.' }
    Write-Host 'Da Update Git.' -ForegroundColor Green
}
