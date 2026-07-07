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
        image="clawbench-harbor:latest",
        model_name="policy",
        num_samples=4,
        timeout_seconds=600,
        harness="hermes",
        dataset_name="clawbench-v2",
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

    # runtime prepares the browser env
    types = [p["type"] for p in payload["runtime"]["prepare"]]
    assert "upload_dir" in types and "exec" in types
    assert payload["num_samples"] == 4


def test_run_script_routes_policy_but_not_judge() -> None:
    """The episode's policy model uses $OPENAI_BASE_URL; the judge must not."""
    text = submit.RUN_SCRIPT.read_text()
    # policy is routed through the captured gateway endpoint
    assert 'CLAWBENCH_BASE_URL="${OPENAI_BASE_URL}"' in text
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
