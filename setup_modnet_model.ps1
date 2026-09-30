$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "ERROR: .venv was not created. Run setup_windows.bat again." -ForegroundColor Red
    exit 1
}

$modelDir = Join-Path $PSScriptRoot "backend\models"
$modelPath = Join-Path $modelDir "modnet_photographic_portrait_matting.onnx"
New-Item -ItemType Directory -Force -Path $modelDir | Out-Null

$needDownload = $true
if (Test-Path -LiteralPath $modelPath) {
    $size = (Get-Item -LiteralPath $modelPath).Length
    if ($size -gt 1000000) { $needDownload = $false }
}

if ($needDownload) {
    Write-Host "`n==> Downloading official MODNet ONNX portrait-matting model" -ForegroundColor Cyan
    Write-Host "This is downloaded once and then runs locally on your PC."
    & $python -m gdown "https://drive.google.com/uc?id=1cgycTQlYXpTh26gB9FTnthE7AvruV8hd" -O $modelPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: MODNet model download failed." -ForegroundColor Red
        exit 1
    }
}

$size = (Get-Item -LiteralPath $modelPath).Length
if ($size -le 1000000) {
    Write-Host "ERROR: MODNet model file is incomplete." -ForegroundColor Red
    exit 1
}

Write-Host "`n==> Testing MODNet ONNX Runtime" -ForegroundColor Cyan
& $python -c "import sys; sys.path.insert(0, r'$PSScriptRoot\backend'); from modnet_background import ModNetMatting; m=ModNetMatting(r'$modelPath'); assert m.available; print('MODNet provider ready:', r'$modelPath')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: MODNet provider self-test failed." -ForegroundColor Red
    exit 1
}

Write-Host "MODNet local portrait matting is ready." -ForegroundColor Green
exit 0
