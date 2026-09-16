$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Stop-WithHelp([string]$Message) {
    Write-Host "`nERROR: $Message" -ForegroundColor Red
    exit 1
}

function Find-SupportedPython {
    $candidates = @(
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3.11") },
        @{ Command = "py"; Args = @("-3.10") },
        @{ Command = "python"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) { continue }
        try {
            $versionText = & $candidate.Command @($candidate.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $versionText -match '^3\.(10|11|12)$') {
                return $candidate
            }
        } catch { }
    }
    return $null
}

Write-Host "Photo Enhancer - Windows Setup" -ForegroundColor Green
Write-Host "This may take 10-20 minutes on the first installation."

Write-Step "Checking Python"
$python = Find-SupportedPython
if ($null -eq $python) {
    Stop-WithHelp "Python 3.10, 3.11, or 3.12 was not found. Install Python 3.12 from python.org, select 'Add Python to PATH', then run this file again."
}
$pythonVersion = & $python.Command @($python.Args) --version
Write-Host "Found $pythonVersion" -ForegroundColor Green

Write-Step "Checking Node.js and npm"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Stop-WithHelp "Node.js was not found. Install the Node.js LTS version from nodejs.org, restart the PC, then run setup_windows.bat again."
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Stop-WithHelp "npm was not found. Reinstall the Node.js LTS version, then run setup_windows.bat again."
}
$nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
if ($nodeMajor -lt 18) {
    Stop-WithHelp "Node.js 18 or newer is required. Install the current Node.js LTS version."
}
Write-Host "Found Node.js $(& node --version) and npm $(& npm.cmd --version)" -ForegroundColor Green

Write-Step "Creating the private Python environment"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $python.Command @($python.Args) -m venv (Join-Path $PSScriptRoot ".venv")
    if ($LASTEXITCODE -ne 0) { Stop-WithHelp "Python could not create the .venv environment." }
}

Write-Step "Installing Python packages"
& $venvPython -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { Stop-WithHelp "pip could not be updated. Check your internet connection." }
& $venvPython -m pip install -r (Join-Path $PSScriptRoot "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { Stop-WithHelp "Backend packages could not be installed. Check the error shown above." }

Write-Step "Installing the web interface"
Push-Location (Join-Path $PSScriptRoot "frontend")
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { Stop-WithHelp "Frontend packages could not be installed." }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { Stop-WithHelp "The frontend test build failed." }
} finally {
    Pop-Location
}

Write-Step "Downloading the background-removal AI model"
Write-Host "The model is about 176 MB. Please wait until it finishes."
& $venvPython -c "from rembg import new_session; new_session('u2net_human_seg'); print('Portrait background-removal model is ready.')"
if ($LASTEXITCODE -ne 0) { Stop-WithHelp "The AI model download failed. Check your internet connection and run setup again." }

Write-Step "Running final checks"
& $venvPython -c "import cv2, mediapipe, fastapi, rembg; from backend.app import app; print('Backend check passed.')"
if ($LASTEXITCODE -ne 0) { Stop-WithHelp "A backend package failed its final check." }

Write-Host "`nSETUP COMPLETE" -ForegroundColor Green
Write-Host "Now double-click run_windows.bat."
exit 0
