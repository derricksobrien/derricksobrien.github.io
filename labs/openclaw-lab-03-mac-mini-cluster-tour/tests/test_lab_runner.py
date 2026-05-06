import json

import pytest

from src import guacamole_hooks, lab_runner


def test_build_lab_prompt_contains_expected_keywords() -> None:
    prompt = lab_runner.build_lab_prompt().lower()
    assert "openclaw" in prompt
    assert "observability" in prompt


def test_dry_run_message_has_bullets() -> None:
    text = lab_runner.call_openclaw_dry("demo")
    assert "- This lab demonstrates" in text
    assert "Best practice" in text


def test_stage0_preflight_passes_without_guacamole_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GUACAMOLE_BASE_URL", raising=False)
    monkeypatch.delenv("GUACAMOLE_CONNECTION_ID", raising=False)
    result = lab_runner.run_preflight()
    assert result.ok is True
    assert result.stage == "stage0_preflight"
    assert "placeholder" in result.details


def test_stage1_access_passes_in_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_ACCESS_TOKEN", raising=False)
    result = lab_runner.run_access_check(live_run=False)
    assert result.ok is True


def test_stage1_access_fails_in_live_run_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_ACCESS_TOKEN", raising=False)
    result = lab_runner.run_access_check(live_run=True)
    assert result.ok is False
    assert "OPENCLAW_ACCESS_TOKEN" in result.details


def test_stage1_access_passes_in_live_run_with_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCLAW_ACCESS_TOKEN", "openclaw-test-token")
    result = lab_runner.run_access_check(live_run=True)
    assert result.ok is True
    assert "present" in result.details


def test_stage2_is_skipped_when_live_run_has_no_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCLAW_ACCESS_TOKEN", raising=False)
    results, _prompt, _response = lab_runner.run(stage="all", live_run=True)
    stage2 = next(result for result in results if result.stage == "stage2_cluster_walkthrough")
    assert stage2.ok is False
    assert "skipped" in stage2.details


def test_single_stage0_only_returns_one_result() -> None:
    results, _prompt, _response = lab_runner.run(stage="stage0", live_run=False)
    assert len(results) == 1
    assert results[0].stage == "stage0_preflight"


def test_single_stage3_stream_returns_chunks() -> None:
    results, _prompt, _response = lab_runner.run(stage="stage3", live_run=False)
    assert len(results) == 1
    assert results[0].stage == "stage3_walkthrough_stream"
    assert "chunks=" in results[0].details


def test_artifact_written_to_disk(tmp_path: pytest.FixtureDef, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lab_runner, "ARTIFACTS_DIR", tmp_path)
    results, prompt, response_text = lab_runner.run(stage="all", live_run=False)
    run_record = lab_runner.LabRun(
        mode="dry-run",
        timestamp_utc="2026-01-01T00:00:00+00:00",
        prompt=prompt,
        response=response_text,
        stage_results=results,
    )
    artifact = lab_runner.write_artifact(run_record)
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["mode"] == "dry-run"
    assert len(payload["stage_results"]) > 0


def test_guacamole_check_session_ready_stub_passes() -> None:
    ok, detail = guacamole_hooks.check_session_ready()
    assert ok is True
    assert isinstance(detail, str)


def test_guacamole_open_lab_session_stub_passes() -> None:
    ok, detail = guacamole_hooks.open_lab_session("Test Participant")
    assert ok is True
    assert isinstance(detail, str)


def test_guacamole_close_lab_session_stub_does_not_raise() -> None:
    guacamole_hooks.close_lab_session("fake-token")