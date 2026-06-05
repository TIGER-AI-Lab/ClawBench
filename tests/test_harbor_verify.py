"""Tests for clawbench.harbor.verify reward logic against fixture interceptions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawbench.harbor import verify


def _write_interception(data_dir: Path, *, intercepted: bool) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    blob = {
        "intercepted": intercepted,
        "stop_reason": "eval_matched" if intercepted else "time_limit_exceeded",
        "request": (
            {
                "url": "https://myrecipes.com/collections/bookmarks/save",
                "method": "POST",
                "body": {"recipe": "Baked Ziti", "collection": "Want to Try"},
            }
            if intercepted
            else None
        ),
        "schema": {"url_pattern": "save", "method": "POST"},
    }
    (data_dir / "interception.json").write_text(json.dumps(blob, indent=2))
    # Minimal supporting files so classify_run does not crash.
    (data_dir / "actions.jsonl").write_text("")
    (data_dir / "requests.jsonl").write_text("")
    (data_dir / "agent-messages.jsonl").write_text("")


JUDGE_CFG = {
    "model": "gemini-3.5-flash",
    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
    "api_type": "openai-completions",
    "api_key": "k",
}


def _patch_judge(monkeypatch: pytest.MonkeyPatch, match: bool | None) -> None:
    def fake_judge_request(model_cfg, judge_model_name, instruction, intercept, **kw):
        return {
            "match": match,
            "reason": "stubbed",
            "judge_model": judge_model_name,
            "raw": None,
            "error": None,
        }

    monkeypatch.setattr("clawbench.runner.judge.judge_request", fake_judge_request)


def test_intercepted_and_judge_match_is_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _write_interception(data, intercepted=True)
    _patch_judge(monkeypatch, True)
    result = verify.compute_reward(
        data, no_judge=False, judge_cfg=JUDGE_CFG, instruction="Add Baked Ziti"
    )
    assert result["intercepted"] is True
    assert result["judge_match"] is True
    assert result["pass"] is True
    assert result["reward"] == 1.0


def test_intercepted_but_judge_mismatch_is_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _write_interception(data, intercepted=True)
    _patch_judge(monkeypatch, False)
    result = verify.compute_reward(
        data, no_judge=False, judge_cfg=JUDGE_CFG, instruction="Add Baked Ziti"
    )
    assert result["intercepted"] is True
    assert result["judge_match"] is False
    assert result["pass"] is False
    assert result["reward"] == 0.0


def test_intercepted_judge_inconclusive_is_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _write_interception(data, intercepted=True)
    _patch_judge(monkeypatch, None)
    result = verify.compute_reward(
        data, no_judge=False, judge_cfg=JUDGE_CFG, instruction="Add Baked Ziti"
    )
    assert result["judge_match"] is None
    assert result["pass"] is False
    assert result["reward"] == 0.0


def test_not_intercepted_is_fail_and_judge_not_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _write_interception(data, intercepted=False)

    def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("judge must not run when not intercepted")

    monkeypatch.setattr("clawbench.runner.judge.judge_request", boom)
    result = verify.compute_reward(
        data, no_judge=False, judge_cfg=JUDGE_CFG, instruction="Add Baked Ziti"
    )
    assert result["intercepted"] is False
    assert result["judge"] is None
    assert result["pass"] is False
    assert result["reward"] == 0.0


def test_no_judge_intercepted_is_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _write_interception(data, intercepted=True)

    def boom(*a, **k):  # pragma: no cover - must not be called
        raise AssertionError("judge must not run with no_judge=True")

    monkeypatch.setattr("clawbench.runner.judge.judge_request", boom)
    result = verify.compute_reward(data, no_judge=True, judge_cfg=None, instruction="")
    assert result["intercepted"] is True
    assert result["pass"] is True
    assert result["reward"] == 1.0


def test_no_judge_not_intercepted_is_fail(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_interception(data, intercepted=False)
    result = verify.compute_reward(data, no_judge=True, judge_cfg=None, instruction="")
    assert result["pass"] is False
    assert result["reward"] == 0.0


def test_main_writes_reward_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    _write_interception(data, intercepted=True)
    reward_file = tmp_path / "logs" / "verifier" / "reward.txt"
    rc = verify.main(
        ["--data-dir", str(data), "--reward-file", str(reward_file), "--no-judge"]
    )
    assert rc == 0
    assert reward_file.read_text().strip() == "1.0"
    blob = json.loads((reward_file.parent / "verify-result.json").read_text())
    assert blob["reward"] == 1.0
    assert blob["intercepted"] is True


def test_ensure_interception_creates_file_when_missing(tmp_path: Path) -> None:
    # No interception.json: ensure_interception should synthesize a not-intercepted
    # result from the stop-reason marker, and reward should be 0.
    data = tmp_path / "data"
    data.mkdir(parents=True)
    (data / ".stop-reason").write_text("time_limit_exceeded")
    result = verify.compute_reward(data, no_judge=True, judge_cfg=None, instruction="")
    assert (data / "interception.json").exists()
    assert result["intercepted"] is False
    assert result["reward"] == 0.0
