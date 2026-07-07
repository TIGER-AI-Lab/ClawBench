"""Tests for staging + payload construction in clawbench.prorl.submit."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawbench.eval.harbor_adapter import DEFAULT_CASES_DIR, discover_cases
from clawbench.prorl import submit


@pytest.fixture(scope="module")
def one_case():
    cases = discover_cases(DEFAULT_CASES_DIR)
    if not cases:
        pytest.skip("no bundled V2 cases available")
    return cases[0]


@pytest.fixture
def staged(one_case, tmp_path: Path):
    task_dir, task = one_case
    dest = submit.stage_task(
        task_dir,
        task,
        tmp_path,
        org="clawbench",
        dataset_name="clawbench-v2",
        output_name="case",
    )
    return task_dir, dest


def test_stage_produces_instruction_and_tests(staged) -> None:
    _, dest = staged
    step = dest / "steps" / "run"
    assert (step / "instruction.md").is_file()
    assert (step / "tests" / "test.sh").is_file()
    assert (step / "workdir" / "setup.sh").is_file()


def test_build_task_request_shape(staged) -> None:
    task_dir, dest = staged
    req = submit.build_task_request(
        dest,
        task_id=task_dir.name,
        image="clawbench-hermes:latest",
        model_name="policy",
        num_samples=4,
        timeout_seconds=600,
        dataset_name="clawbench-v2",
        judge_env={
            "CLAWBENCH_JUDGE_MODEL": "glm-5.1",
            "CLAWBENCH_JUDGE_BASE_URL": "https://judge.example/v1",
            "CLAWBENCH_JUDGE_API_KEY": "sk-judge",
        },
    )
    payload = req.to_payload()

    # shell harness drives run-prorl.sh
    assert payload["agent"]["harness"] == "shell"
    assert payload["agent"]["custom_shell"]["command"].endswith("run-prorl.sh")
    assert payload["agent"]["env"]["POLAR_MODEL_NAME"] == "policy"

    # harbor evaluator points at the staged tests dir
    ev = payload["evaluator"]
    assert ev["strategy"] == "harbor"
    assert ev["refresh_runtime"] is False
    assert Path(ev["config"]["tests_dir"]).name == "tests"
    assert (Path(ev["config"]["tests_dir"]) / "test.sh").is_file()

    # judge config is carried in the evaluator env, independent of the policy
    assert ev["env"]["CLAWBENCH_JUDGE_MODEL"] == "glm-5.1"
    assert ev["env"]["CLAWBENCH_JUDGE_BASE_URL"] == "https://judge.example/v1"

    # runtime prepares the browser env + uploads the Harbor runtime scripts the
    # staged setup.sh/verify.py reference
    prepare = payload["runtime"]["prepare"]
    types = [p["type"] for p in prepare]
    assert "upload_dir" in types and "exec" in types
    assert any(p.get("target") == "/app/src/harbor" for p in prepare), (
        "harbor runtime scripts must be uploaded so a harness image resolves "
        "the staged setup.sh/verify.py"
    )
    assert payload["num_samples"] == 4


def test_run_script_routes_policy_but_not_judge() -> None:
    """The episode's policy model uses $OPENAI_BASE_URL; the judge must not."""
    text = submit.RUN_SCRIPT.read_text()
    # policy is routed through the captured gateway endpoint via the env vars
    # the ClawBench harness runners actually read.
    assert 'BASE_URL="${OPENAI_BASE_URL}"' in text
    assert 'API_KEY="${OPENAI_API_KEY}"' in text
    # the harness setup needs the browser CDP endpoint (entrypoint is bypassed)
    assert "CLAWBENCH_BROWSER_CDP_URL" in text
    # the judge endpoint is never derived from the gateway endpoint
    for line in text.splitlines():
        if "CLAWBENCH_JUDGE_BASE_URL" in line:
            assert "OPENAI_BASE_URL" not in line, (
                "judge endpoint must not reuse the gateway proxy — it would "
                "pollute the trajectory with judge tokens"
            )


def test_dry_run_prints_valid_payload(one_case, capsys, tmp_path: Path) -> None:
    task_dir, _ = one_case
    rc = submit.main(
        [
            "--task",
            task_dir.name,
            "--dry-run",
            "--staging-dir",
            str(tmp_path / "stage"),
            "--model-name",
            "policy",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["task_id"] == task_dir.name
    assert payload["agent"]["harness"] == "shell"
    assert payload["evaluator"]["strategy"] == "harbor"


def test_poll_completed_returns(monkeypatch) -> None:
    seq = iter([{"status": "running"}, {"status": "completed", "sessions": []}])
    monkeypatch.setattr(submit, "_get_json", lambda url, timeout=30.0: next(seq))
    status = submit.poll_task("http://x", "t1", interval=0, max_wait=5)
    assert status["status"] == "completed"


def test_poll_failed_raises(monkeypatch) -> None:
    monkeypatch.setattr(
        submit,
        "_get_json",
        lambda url, timeout=30.0: {"status": "failed", "error": "boom"},
    )
    with pytest.raises(RuntimeError, match="failed"):
        submit.poll_task("http://x", "t1", interval=0, max_wait=5)


def test_poll_unexpected_status_raises(monkeypatch) -> None:
    monkeypatch.setattr(submit, "_get_json", lambda url, timeout=30.0: {"status": ""})
    with pytest.raises(RuntimeError, match="unexpected status"):
        submit.poll_task("http://x", "t1", interval=0, max_wait=5)
