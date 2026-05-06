from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

try:
    from src import guacamole_hooks
except ImportError:
    import guacamole_hooks  # type: ignore[no-redef]


ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
DEFAULT_CLUSTER_URL = "https://openclaw.example.internal"
DEFAULT_CLUSTER_NAME = "openclaw-6x-mac-mini"


@dataclass
class StageResult:
    stage: str
    ok: bool
    details: str
    duration_ms: int


@dataclass
class LabRun:
    mode: str
    timestamp_utc: str
    prompt: str
    response: str
    stage_results: list[StageResult]


def run_preflight() -> StageResult:
    start = time.perf_counter()
    checks: list[str] = []

    if os.getenv("GUACAMOLE_BASE_URL"):
        checks.append("guacamole_url=present")
    else:
        checks.append("guacamole_url=placeholder")

    if os.getenv("GUACAMOLE_CONNECTION_ID"):
        checks.append("guacamole_connection_id=present")
    else:
        checks.append("guacamole_connection_id=placeholder")

    cluster_name = os.getenv("OPENCLAW_CLUSTER_NAME", DEFAULT_CLUSTER_NAME)
    checks.append(f"cluster={cluster_name}")

    guac_ok, guac_detail = guacamole_hooks.check_session_ready()
    checks.append(f"guac_session={guac_detail}")

    details = ", ".join(checks)
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage0_preflight", guac_ok, details, duration)


def run_access_check(live_run: bool) -> StageResult:
    start = time.perf_counter()
    token_present = bool(os.getenv("OPENCLAW_ACCESS_TOKEN"))

    if live_run and not token_present:
        duration = int((time.perf_counter() - start) * 1000)
        return StageResult("stage1_access_check", False, "LIVE_RUN requested but OPENCLAW_ACCESS_TOKEN missing", duration)

    details = "Access token present" if token_present else "Dry-run mode, no cluster token needed"
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage1_access_check", True, details, duration)


def build_lab_prompt() -> str:
    return (
        "You are assisting a self-guided lab participant. "
        "Provide a concise summary of what this OpenClaw 6-node Mac Mini cluster tour demonstrates in 5 bullet points. "
        "Include one best practice for remote session hygiene and one for cluster observability."
    )


def call_openclaw_live(prompt: str) -> str:
    access_token = os.getenv("OPENCLAW_ACCESS_TOKEN", "").strip()
    if not access_token:
        raise ValueError("OPENCLAW_ACCESS_TOKEN is not set or empty")

    cluster_url = os.getenv("OPENCLAW_CLUSTER_URL", DEFAULT_CLUSTER_URL).rstrip("/")

    response = requests.post(
        f"{cluster_url}/api/tour/summary",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"prompt": prompt},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("summary", "")).strip()


def call_openclaw_dry(prompt: str) -> str:
    _ = prompt
    return (
        "- This lab demonstrates guided access to a 6-node Mac Mini cluster.\n"
        "- It shows how operators can present system layout, node roles, and session boundaries.\n"
        "- It highlights remote desktop flow, safe handoff, and reset timing between guests.\n"
        "- It introduces observability checks such as node reachability and session health.\n"
        "- It records run artifacts for post-session review.\n"
        "Best practice (session hygiene): reset credentials and desktop state between participants.\n"
        "Best practice (observability): verify node health and connection latency before each tour."
    )


def run_cluster_stage(live_run: bool, prompt: str) -> tuple[StageResult, str]:
    start = time.perf_counter()
    try:
        text = call_openclaw_live(prompt) if live_run else call_openclaw_dry(prompt)
        duration = int((time.perf_counter() - start) * 1000)
        mode_details = "live-run" if live_run else "dry-run"
        return StageResult("stage2_cluster_walkthrough", True, mode_details, duration), text
    except Exception as exc:
        duration = int((time.perf_counter() - start) * 1000)
        return StageResult("stage2_cluster_walkthrough", False, str(exc), duration), ""


def run_stream_simulation(text: str) -> StageResult:
    start = time.perf_counter()
    chunks = [text[i : i + 80] for i in range(0, len(text), 80)]
    _ = chunks
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage3_walkthrough_stream", True, f"chunks={len(chunks)}", duration)


def write_artifact(lab_run: LabRun) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = ARTIFACTS_DIR / f"run-{stamp}.json"

    payload = {
        "mode": lab_run.mode,
        "timestamp_utc": lab_run.timestamp_utc,
        "prompt": lab_run.prompt,
        "response": lab_run.response,
        "stage_results": [asdict(stage_result) for stage_result in lab_run.stage_results],
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def run(stage: str, live_run: bool) -> tuple[list[StageResult], str, str]:
    results: list[StageResult] = []
    prompt = build_lab_prompt()
    response_text = ""

    if stage in {"stage0", "all"}:
        results.append(run_preflight())
    if stage in {"stage1", "all"}:
        access_result = run_access_check(live_run)
        results.append(access_result)
        if not access_result.ok:
            if stage in {"stage2", "all"}:
                results.append(StageResult("stage2_cluster_walkthrough", False, "skipped: access failed", 0))
            if stage in {"stage3", "all"}:
                response_text = call_openclaw_dry(prompt)
                results.append(run_stream_simulation(response_text))
            return results, prompt, response_text

    if stage in {"stage2", "all"}:
        result, response_text = run_cluster_stage(live_run, prompt)
        results.append(result)

    if stage in {"stage3", "all"}:
        if not response_text:
            response_text = call_openclaw_dry(prompt)
        results.append(run_stream_simulation(response_text))

    return results, prompt, response_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run OpenClaw Lab 03 self-guided script")
    parser.add_argument(
        "--stage",
        choices=["stage0", "stage1", "stage2", "stage3", "all"],
        default="all",
        help="Stage to run",
    )
    parser.add_argument("--live-run", action="store_true", help="Run the cluster tour against a live OpenClaw endpoint")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    results, prompt, response_text = run(args.stage, args.live_run)

    failed = [result for result in results if not result.ok]
    run_record = LabRun(
        mode="live-run" if args.live_run else "dry-run",
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        prompt=prompt,
        response=response_text,
        stage_results=results,
    )
    artifact = write_artifact(run_record)

    print(f"Artifact written: {artifact}")
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"[{status}] {result.stage} - {result.details} ({result.duration_ms} ms)")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())