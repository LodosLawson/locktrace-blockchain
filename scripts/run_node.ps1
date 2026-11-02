# ========================================================
# LockTrace Community Node Launcher for Windows PowerShell
# ========================================================
Write-Host "=== 🛡️ LockTrace Node Setup for Windows ===" -ForegroundColor Cyan

# Check Python
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (!$pyCmd) {
    $pyCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (!$pyCmd) {
    Write-Error "Python 3 is not found in PATH. Please install Python from https://python.org"
    exit 1
}

if (!(Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    & $pyCmd.Source -m venv venv
}

& ".\venv\Scripts\Activate.ps1"
pip install -q --upgrade pip
pip install -q -r requirements.txt

$name = Read-Host "Enter your Node Name (e.g., Windows-Peer-01)"
if ([string]::IsNullOrWhiteSpace($name)) { $name = "Windows-Community-Peer" }

$loc = Read-Host "Enter your Geographic Location (e.g., Ankara, TR)"
if ([string]::IsNullOrWhiteSpace($loc)) { $loc = "Global" }

Write-Host "Starting LockTrace Node daemon..." -ForegroundColor Green
python node_runner.py --name "$name" --location "$loc"
