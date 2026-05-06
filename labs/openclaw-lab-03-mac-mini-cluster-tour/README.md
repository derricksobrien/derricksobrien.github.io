# OpenClaw Lab 03: Mac Mini Cluster Tour (Self-Guided Tour)

This is a simple, cloneable lab repo for your third free tour experience.

The flow is split into stages so you can run it quickly in a 45-minute session and customize it later for your Guacamole-based remote access.

## Lab Stages

1. Stage 0 - Access + environment preflight
2. Stage 1 - Cluster access check
3. Stage 2 - Run a first cluster tour step (dry-run by default)
4. Stage 3 - Simulate operator walkthrough output and capture transcript
5. Stage 4 - Export artifacts and optional debrief prompts

## Why dry-run by default

Most promo users do not have remote cluster credentials ready. The script runs safely in dry-run mode unless you opt into live requests.

- Dry-run: no external cluster call, deterministic output
- Live-run: set `LIVE_RUN=1` and provide `OPENCLAW_ACCESS_TOKEN`

## Quick Start

```powershell
Set-Location labs/openclaw-lab-03-mac-mini-cluster-tour
powershell -ExecutionPolicy Unrestricted -File .\scripts\setup.ps1
powershell -ExecutionPolicy Unrestricted -File .\scripts\run-lab.ps1 -Stage all
```

## Live Cluster Run (optional)

1. Copy `.env.example` to `.env`
2. Set `OPENCLAW_ACCESS_TOKEN`
3. Run:

```powershell
powershell -ExecutionPolicy Unrestricted -File .\scripts\run-lab.ps1 -Stage all -LiveRun
```

## Guacamole Nuance Hooks

The following values are included as placeholders so you can adapt access policy without changing core stage logic:

- `GUACAMOLE_BASE_URL`
- `GUACAMOLE_CONNECTION_ID`
- `GUACAMOLE_LAB_NOTES`

Where to customize:

- Access checks: `src/lab_runner.py` in `run_preflight`
- Stage messaging copy: `src/lab_runner.py` in `build_lab_prompt`
- Operator prompts for your support team: `scripts/run-lab.ps1`

## Outputs

Each run writes an artifact file to `artifacts/`:

- `run-YYYYMMDD-HHMMSS.json`

Fields include stage statuses, mode (`dry-run` or `live-run`), prompt, response, and timing.