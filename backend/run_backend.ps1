Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment not found. Run setup_backend.ps1 first."
}

if (-not $env:ALLOWED_ORIGINS) {
    $env:ALLOWED_ORIGINS = "http://localhost:8000,http://127.0.0.1:8000"
}

if (-not $env:FLASK_SECRET_KEY) {
    $env:FLASK_SECRET_KEY = "dev-only-secret"
}

if (-not $env:PORT) {
    $env:PORT = "5050"
}

& ".\.venv\Scripts\python.exe" .\app.py