from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

try:
    from src import guacamole_hooks
except ImportError:
    import guacamole_hooks  # type: ignore[no-redef]


ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"


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

    guac_ok, guac_detail = guacamole_hooks.check_session_ready()
    checks.append(f"guac_session={guac_detail}")

    details = ", ".join(checks)
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage0_preflight", guac_ok, details, duration)


def run_auth_check(live_run: bool) -> StageResult:
    start = time.perf_counter()
    key_present = bool(os.getenv("NVIDIA_API_KEY"))

    if live_run and not key_present:
        duration = int((time.perf_counter() - start) * 1000)
        return StageResult("stage1_auth_check", False, "LIVE_RUN requested but NVIDIA_API_KEY missing", duration)

    details = "API key present" if key_present else "Dry-run mode, no API key needed"
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage1_auth_check", True, details, duration)


def build_lab_prompt() -> str:
    return (
        "You are assisting a self-guided lab participant. "
        "Provide a concise summary of what this NVIDIA Blackwell GPU inference lab demonstrates in 5 bullet points. "
        "Include one best practice for model selection and one for throughput tuning."
    )


def call_nvidia_live(prompt: str) -> str:
    api_key = os.getenv("NVIDIA_API_KEY", "").strip()
    if not api_key:
        raise ValueError("NVIDIA_API_KEY is not set or empty")

    base_url = os.getenv("NVIDIA_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = os.getenv("NVIDIA_MODEL", DEFAULT_MODEL)
    max_tokens = int(os.getenv("NVIDIA_MAX_TOKENS", "512"))

    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.2,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    return payload["choices"][0]["message"]["content"].strip()


def call_nvidia_dry(prompt: str) -> str:
    _ = prompt
    return (
        "- This lab demonstrates hosted GPU inference on a Blackwell-ready stack.\n"
        "- It shows how a client sends a structured prompt to a model endpoint.\n"
        "- It highlights model choice, latency expectations, and token budgeting.\n"
        "- It introduces concurrency, batching, and observability considerations.\n"
        "- It records run artifacts for post-session review.\n"
        "Best practice (model selection): start with the smallest model that meets quality needs.\n"
        "Best practice (throughput): batch predictable work and measure latency at realistic concurrency."
    )


def run_message_stage(live_run: bool, prompt: str) -> tuple[StageResult, str]:
    start = time.perf_counter()
    try:
        text = call_nvidia_live(prompt) if live_run else call_nvidia_dry(prompt)
        duration = int((time.perf_counter() - start) * 1000)
        mode_details = "live-run" if live_run else "dry-run"
        return StageResult("stage2_first_inference", True, mode_details, duration), text
    except Exception as exc:
        duration = int((time.perf_counter() - start) * 1000)
        return StageResult("stage2_first_inference", False, str(exc), duration), ""


def run_stream_simulation(text: str) -> StageResult:
    start = time.perf_counter()
    chunks = [text[i : i + 80] for i in range(0, len(text), 80)]
    _ = chunks
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage3_stream_simulation", True, f"chunks={len(chunks)}", duration)


def write_artifact(lab_run: LabRun) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_path = ARTIFACTS_DIR / f"run-{stamp}.json"

    payload = {
        "mode": lab_run.mode,
        "timestamp_utc": lab_run.timestamp_utc,
        "prompt": lab_run.prompt,
        "response": lab_run.response,
        "stage_results": [asdict(s) for s in lab_run.stage_results],
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
        auth_result = run_auth_check(live_run)
        results.append(auth_result)
        if not auth_result.ok:
            if stage in {"stage2", "all"}:
                results.append(StageResult("stage2_first_inference", False, "skipped: auth failed", 0))
            if stage in {"stage3", "all"}:
                response_text = call_nvidia_dry(prompt)
                results.append(run_stream_simulation(response_text))
            return results, prompt, response_text

    if stage in {"stage2", "all"}:
        result, response_text = run_message_stage(live_run, prompt)
        results.append(result)

    if stage in {"stage3", "all"}:
        if not response_text:
            response_text = call_nvidia_dry(prompt)
        results.append(run_stream_simulation(response_text))

    return results, prompt, response_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NVIDIA Lab 02 self-guided script")
    parser.add_argument(
        "--stage",
        choices=["stage0", "stage1", "stage2", "stage3", "all"],
        default="all",
        help="Stage to run",
    )
    parser.add_argument("--live-run", action="store_true", help="Call NVIDIA inference API live")
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