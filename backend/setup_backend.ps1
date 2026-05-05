Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Unrestricted -Force

$pythonExe = "C:/Users/derri/AppData/Local/Python/pythoncore-3.14-64/python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found at $pythonExe"
}

if (-not (Test-Path ".venv")) {
    & $pythonExe -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt

Write-Host "Backend environment is ready."