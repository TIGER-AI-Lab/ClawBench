"""Unit tests for the Polar TaskRequest models."""

from __future__ import annotations

import pytest

from clawbench.prorl.models import (
    AgentSpec,
    EvaluatorSpec,
    PrepareAction,
    RuntimeSpec,
    TaskRequest,
)


def _minimal_request(**overrides) -> TaskRequest:
    kwargs = dict(
        task_id="v2-001",
        instruction="do the thing",
        runtime=RuntimeSpec(image="clawbench-harbor:latest"),
        agent=AgentSpec(
            model_name="policy",
            harness="shell",
            custom_shell={"command": "bash /app/run-prorl.sh"},
        ),
        evaluator=EvaluatorSpec(strategy="harbor", config={"tests_dir": "/x"}),
    )
    kwargs.update(overrides)
    return TaskRequest(**kwargs)


def test_task_request_payload_has_contract_keys() -> None:
    payload = _minimal_request().to_payload()
    for key in (
        "task_id",
        "instruction",
        "num_samples",
        "timeout_seconds",
        "runtime",
        "agent",
        "builder",
        "evaluator",
    ):
        assert key in payload
    assert payload["builder"]["strategy"] == "prefix_merging"
    assert payload["runtime"]["backend"] == "docker"
    assert payload["evaluator"]["strategy"] == "harbor"
    assert payload["evaluator"]["refresh_runtime"] is False


def test_shell_agent_requires_custom_shell() -> None:
    with pytest.raises(ValueError, match="custom_shell"):
        AgentSpec(model_name="p", harness="shell")


def test_agent_exactly_one_of_harness_or_import_path() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        AgentSpec(model_name="p", harness="shell", import_path="m:C")
    # custom_shell may not accompany an import_path harness
    with pytest.raises(ValueError, match="only valid with harness='shell'"):
        AgentSpec(
            model_name="p",
            harness=None,
            import_path="m:C",
            custom_shell={"command": "x"},
        )


def test_agent_payload_shape() -> None:
    payload = AgentSpec(
        model_name="policy",
        harness="shell",
        custom_shell={"command": "bash /app/run-prorl.sh"},
        env={"POLAR_MODEL_NAME": "policy"},
    ).to_payload()
    assert payload["harness"] == "shell"
    assert payload["custom_shell"]["command"].endswith("run-prorl.sh")
    assert payload["model_name"] == "policy"
    assert "import_path" not in payload  # None dropped


def test_prepare_action_validation() -> None:
    with pytest.raises(ValueError, match="requires source and target"):
        PrepareAction(type="upload_dir", source="a")
    with pytest.raises(ValueError, match="exec requires command"):
        PrepareAction(type="exec")
    with pytest.raises(ValueError, match="type must be one of"):
        PrepareAction(type="bogus")
    ok = PrepareAction(type="exec", command="bash /app/setup.sh", cwd="/app")
    assert ok.to_payload() == {
        "type": "exec",
        "command": "bash /app/setup.sh",
        "cwd": "/app",
    }


def test_num_samples_and_timeout_guards() -> None:
    with pytest.raises(ValueError, match="num_samples"):
        _minimal_request(num_samples=0)
    with pytest.raises(ValueError, match="timeout_seconds"):
        _minimal_request(timeout_seconds=0)
