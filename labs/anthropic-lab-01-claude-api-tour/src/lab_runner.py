from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

try:
    from src import guacamole_hooks  # when imported as package (pytest)
except ImportError:
    import guacamole_hooks  # type: ignore[no-redef]  # when run directly


ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
DEFAULT_MODEL = "claude-3-5-sonnet-latest"


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

    # --- GUACAMOLE HOOK: session readiness check ---
    # Replace the stub with real connection validation once you wire Guacamole.
    guac_ok, guac_detail = guacamole_hooks.check_session_ready()
    checks.append(f"guac_session={guac_detail}")

    details = ", ".join(checks)
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage0_preflight", guac_ok, details, duration)


def run_auth_check(live_run: bool) -> StageResult:
    start = time.perf_counter()
    key_present = bool(os.getenv("ANTHROPIC_API_KEY"))

    if live_run and not key_present:
        duration = int((time.perf_counter() - start) * 1000)
        return StageResult("stage1_auth_check", False, "LIVE_RUN requested but ANTHROPIC_API_KEY missing", duration)

    details = "API key present" if key_present else "Dry-run mode, no API key needed"
    duration = int((time.perf_counter() - start) * 1000)
    return StageResult("stage1_auth_check", True, details, duration)


def build_lab_prompt() -> str:
    return (
        "You are assisting a self-guided lab participant. "
        "Provide a concise summary of what this Claude API lab demonstrates in 5 bullet points. "
        "Include one best practice for prompt structure and one for error handling."
    )


def call_claude_live(prompt: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY is not set or empty")
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_MODEL)
    max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "512"))

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()

    content = payload.get("content", [])
    text_parts = [item.get("text", "") for item in content if item.get("type") == "text"]
    return "\n".join(part for part in text_parts if part.strip())


def call_claude_dry(prompt: str) -> str:
    return (
        "- This lab demonstrates authenticated Claude API requests.\n"
        "- It shows a structured request payload with model and token controls.\n"
        "- It validates a simple workflow from prompt to response capture.\n"
        "- It introduces streaming concepts with chunked output simulation.\n"
        "- It records run artifacts for post-session review.\n"
        "Best practice (prompting): keep instructions explicit and scoped.\n"
        "Best practice (errors): implement retries with backoff and log request context."
    )


def run_message_stage(live_run: bool, prompt: str) -> tuple[StageResult, str]:
    start = time.perf_counter()
    try:
        text = call_claude_live(prompt) if live_run else call_claude_dry(prompt)
        duration = int((time.perf_counter() - start) * 1000)
        mode_details = "live-run" if live_run else "dry-run"
        return StageResult("stage2_first_message", True, mode_details, duration), text
    except Exception as exc:
        duration = int((time.perf_counter() - start) * 1000)
        return StageResult("stage2_first_message", False, str(exc), duration), ""


def run_stream_simulation(text: str) -> StageResult:
    start = time.perf_counter()
    # Intentional simple chunking; replace with real stream event handling for full lab nuance.
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
        # Short-circuit: skip API stages if auth failed in live-run mode.
        if not auth_result.ok:
            if stage in {"stage2", "all"}:
                results.append(StageResult("stage2_first_message", False, "skipped: auth failed", 0))
            if stage in {"stage3", "all"}:
                response_text = call_claude_dry(prompt)
                results.append(run_stream_simulation(response_text))
            return results, prompt, response_text

    if stage in {"stage2", "all"}:
        result, response_text = run_message_stage(live_run, prompt)
        results.append(result)

    if stage in {"stage3", "all"}:
        if not response_text:
            response_text = call_claude_dry(prompt)
        results.append(run_stream_simulation(response_text))

    return results, prompt, response_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Anthropic Lab 01 self-guided script")
    parser.add_argument(
        "--stage",
        choices=["stage0", "stage1", "stage2", "stage3", "all"],
        default="all",
        help="Stage to run",
    )
    parser.add_argument("--live-run", action="store_true", help="Call Anthropic API live")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    results, prompt, response_text = run(args.stage, args.live_run)

    failed = [r for r in results if not r.ok]
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
