"""Host-side result classification and metadata redaction tests."""

from __future__ import annotations

import argparse
import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from clawbench.runner.run_support.results import classify_run


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_classify_run_success_from_synthetic_output(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(data / "actions.jsonl", [{"type": "click"}])
    _write_jsonl(data / "requests.jsonl", [{"url": "https://example.test"}])
    _write_jsonl(data / "agent-messages.jsonl", [{"model_output": {"ok": True}}])
    (data / "screenshots").mkdir()
    (data / "screenshots" / "0001.png").write_bytes(b"png")
    (data / "recording.mp4").write_bytes(b"0" * 1024 * 1024)
    (data / "interception.json").write_text(json.dumps({"stop_reason": "matched"}))

    result = classify_run(tmp_path, intercepted=True)

    assert result["result_category"] == "intercepted"
    assert result["failure_category"] is None
    assert result["infra_failure"] is False
    assert result["metrics"]["actions"] == 1


def test_classify_run_flags_missing_recording(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(data / "actions.jsonl", [{"type": "click"}])
    _write_jsonl(data / "requests.jsonl", [{"url": "https://example.test"}])
    _write_jsonl(data / "agent-messages.jsonl", [{"model_output": {"ok": True}}])
    (data / "screenshots").mkdir()
    (data / "screenshots" / "0001.png").write_bytes(b"png")
    (data / "interception.json").write_text(json.dumps({"stop_reason": "matched"}))

    result = classify_run(tmp_path, intercepted=True)

    assert result["result_category"] == "intercepted"
    assert result["failure_category"] is None
    assert result["infra_failure"] is False
    assert "missing_or_empty_recording" in result["infra_flags"]


def test_classify_run_detects_api_or_credit_evidence(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(data / "agent-messages.jsonl", [])
    (data / "agent.log").write_text("provider returned status code 429\n")

    result = classify_run(tmp_path, intercepted=False)

    assert result["result_category"] == "api_or_credit"
    assert result["failure_category"] == "api_or_credit"
    assert "429" in result["metrics"]["api_or_credit_evidence"]


def test_print_results_includes_usage_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from clawbench.runner.run_support import results

    data = tmp_path / "data"
    data.mkdir()
    _write_jsonl(data / "actions.jsonl", [{"type": "click", "url": "https://e.test"}])
    _write_jsonl(data / "requests.jsonl", [{"url": "https://e.test"}])
    _write_jsonl(data / "agent-messages.jsonl", [])
    (data / "interception.json").write_text(
        json.dumps({"intercepted": True, "stop_reason": "eval_matched"})
    )
    monkeypatch.setattr(
        results,
        "summarize_usage_file",
        lambda _path, model_cfg=None: {
            "status": "estimated",
            "total_tokens": 123,
            "input_tokens": 100,
            "output_tokens": 23,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "reasoning_tokens": 0,
            "estimated_cost_usd": 0.0042,
            "matched_openrouter_model_id": "provider/model",
        },
    )

    assert results.print_results(tmp_path) is True

    out = capsys.readouterr().out
    assert "Usage: 123 total" in out
    assert "estimated cost $0.004200" in out


def test_run_metadata_redacts_model_and_judge_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for module_name in (
        "clawbench.runner.run_support.metadata",
        "clawbench.runner.run_support.docker",
        "clawbench.runner.run_support.config",
    ):
        sys.modules.pop(module_name, None)
    monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
    metadata = importlib.import_module("clawbench.runner.run_support.metadata")
    monkeypatch.setattr(metadata, "container_engine_version", lambda: "docker fake")
    monkeypatch.setattr(metadata, "image_id", lambda _ref: "sha256:fake")

    args = argparse.Namespace(
        test_case_dir=Path("test-cases/v1/001-daily-life-food-uber-eats"),
        human=False,
        model="provider/model",
        harness="openclaw",
        no_build=True,
        no_upload=True,
        judge="judge-model",
        no_judge=False,
        output_dir=tmp_path,
    )
    classification = {
        "result_category": "success",
        "failure_category": None,
        "infra_failure": False,
        "adjusted_eligible": True,
        "infra_flags": [],
        "metrics": {
            "usage": {
                "status": "estimated",
                "total_tokens": 123,
                "estimated_cost_usd": 0.0042,
                "matched_openrouter_model_id": "provider/model",
            }
        },
    }
    model_cfg = {
        "model": "provider/model",
        "api_type": "openai-completions",
        "base_url": "https://api.example.test",
        "api_key": "secret-key",
        "api_keys": ["secret-key", "second-key"],
        "password": "hidden",
    }

    meta = metadata.make_run_meta(
        task={
            "instruction": "Do the thing",
            "eval_schema": {"url_pattern": "example", "method": "POST"},
            "time_limit": 1,
        },
        task_json_sha256="task-sha",
        case_name="001-daily-life-food-uber-eats",
        args=args,
        model_cfg=model_cfg,
        judge_cfg={**model_cfg, "model": "judge-model"},
        task_dir=Path("test-cases/v1/001-daily-life-food-uber-eats"),
        task_file=Path("test-cases/v1/001-daily-life-food-uber-eats/task.json"),
        output_dir=tmp_path,
        container="container",
        run_dir_name="run",
        host_port=6080,
        email="alex@example.test",
        ts="20260101-000000",
        duration=1.2,
        intercepted=True,
        classification=classification,
    )

    dumped = json.dumps(meta)
    assert "secret-key" not in dumped
    assert "second-key" not in dumped
    assert "hidden" not in dumped
    assert meta["model_config"]["api_key_count"] == 2
    assert meta["judge_config"]["api_key_count"] == 2
    assert meta["usage"]["estimated_cost_usd"] == 0.0042
    assert meta["run_metrics"]["usage"]["total_tokens"] == 123
