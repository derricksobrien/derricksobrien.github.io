param(
    [ValidateSet("stage0", "stage1", "stage2", "stage3", "all")]
    [string]$Stage = "all",
    [switch]$LiveRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Unrestricted -Force

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    throw "Missing local venv. Run scripts/setup.ps1 first."
}

if ($LiveRun -and -not (Test-Path ".env")) {
    Write-Warning "Live run requested but .env not found. Create .env from .env.example first."
}

$liveArg = if ($LiveRun) { "--live-run" } else { "" }
& ".\.venv\Scripts\python.exe" .\src\lab_runner.py --stage $Stage $liveArg
