"""Tests for CI harness Dockerfile selection and summary generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clawbench.runner.run_support.harness_build_plan import (
    DEFAULT_BASE_DOCKERFILE,
    discover_harness_dockerfiles,
    format_harness_build_summary,
    main,
    select_harness_build_plan,
)
from clawbench.runner.run_support.harness_registry import HARNESS_REGISTRY

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "check-harness-build.yml"


def test_discover_harness_dockerfiles_matches_registered_harnesses() -> None:
    discovered = discover_harness_dockerfiles(REPO_ROOT)
    expected = tuple(
        sorted(
            path.relative_to(REPO_ROOT).as_posix()
            for path in HARNESS_REGISTRY.harness_dockerfiles.values()
        )
    )

    assert discovered == expected
    assert DEFAULT_BASE_DOCKERFILE not in discovered
    assert len(discovered) == len(HARNESS_REGISTRY.harnesses)


@pytest.mark.parametrize(
    "changed_path",
    [
        "src/clawbench/runtime/runtime-server/server.py",
        "src/clawbench/runtime/runtime-server/pyproject.toml",
        "src/clawbench/runtime/runtime-server/uv.lock",
        "src/clawbench/runtime/harnesses/base/Dockerfile.base",
        "src/clawbench/runtime/harnesses/base/entrypoint.sh",
        "src/clawbench/runtime/chrome-extension/background.js",
        "src/clawbench/runtime/shared/alex_green_personal_info.json",
    ],
)
def test_shared_base_dependencies_select_all_harnesses(changed_path: str) -> None:
    all_dockerfiles = discover_harness_dockerfiles(REPO_ROOT)
    plan = select_harness_build_plan(
        [changed_path],
        event_name="pull_request",
        repo_root=REPO_ROOT,
    )

    assert plan.build_all is True
    assert plan.selection_mode == "all"
    assert plan.selected_dockerfiles == all_dockerfiles
    assert plan.count == len(all_dockerfiles)


def test_single_harness_changes_select_only_affected_harnesses() -> None:
    plan = select_harness_build_plan(
        [
            "src/clawbench/runtime/harnesses/openclaw/run-openclaw.sh",
            "src/clawbench/runtime/harnesses/openclaw/setup-openclaw.sh",
            "src/clawbench/runtime/harnesses/codex/Dockerfile.codex",
        ],
        event_name="pull_request",
        repo_root=REPO_ROOT,
    )

    assert plan.build_all is False
    assert plan.selection_mode == "changed"
    assert plan.selected_dockerfiles == (
        "src/clawbench/runtime/harnesses/codex/Dockerfile.codex",
        "src/clawbench/runtime/harnesses/openclaw/Dockerfile.openclaw",
    )
    assert plan.matrix_dict() == {
        "include": [
            {
                "harness": "codex",
                "dockerfile": "src/clawbench/runtime/harnesses/codex/Dockerfile.codex",
                "image": "clawbench-codex",
            },
            {
                "harness": "openclaw",
                "dockerfile": (
                    "src/clawbench/runtime/harnesses/openclaw/Dockerfile.openclaw"
                ),
                "image": "clawbench-openclaw",
            },
        ]
    }


@pytest.mark.parametrize(
    "irrelevant_path",
    [
        "src/clawbench/runtime/harbor/verify.py",
        "src/clawbench/runtime/harbor/Dockerfile",
        "src/clawbench/runtime/extension-server/server.py",
    ],
)
def test_irrelevant_or_obsolete_runtime_paths_select_zero_harnesses(
    irrelevant_path: str,
) -> None:
    plan = select_harness_build_plan(
        [irrelevant_path],
        event_name="pull_request",
        repo_root=REPO_ROOT,
    )

    assert plan.build_all is False
    assert plan.selection_mode == "changed"
    assert plan.selected_dockerfiles == ()
    assert plan.count == 0
    assert plan.matrix_dict() == {"include": []}


def test_workflow_dispatch_and_empty_runtime_diff_select_all_harnesses() -> None:
    all_dockerfiles = discover_harness_dockerfiles(REPO_ROOT)

    dispatch_plan = select_harness_build_plan(
        ["src/clawbench/runtime/harbor/verify.py"],
        event_name="workflow_dispatch",
        repo_root=REPO_ROOT,
    )
    empty_diff_plan = select_harness_build_plan(
        [],
        event_name="pull_request",
        repo_root=REPO_ROOT,
    )

    assert dispatch_plan.build_all is True
    assert dispatch_plan.selected_dockerfiles == all_dockerfiles
    assert empty_diff_plan.build_all is True
    assert empty_diff_plan.selected_dockerfiles == all_dockerfiles


def test_cli_writes_github_outputs_and_step_summary_for_runtime_server_change(
    tmp_path: Path,
) -> None:
    github_output = tmp_path / "github_output.txt"
    step_summary = tmp_path / "step_summary.md"

    rc = main(
        [
            "--event-name",
            "pull_request",
            "--repo-root",
            str(REPO_ROOT),
            "--github-output",
            str(github_output),
            "--github-step-summary",
            str(step_summary),
            "src/clawbench/runtime/runtime-server/server.py",
        ]
    )

    assert rc == 0
    output_lines = dict(
        line.split("=", 1)
        for line in github_output.read_text(encoding="utf-8").splitlines()
    )
    all_dockerfiles = discover_harness_dockerfiles(REPO_ROOT)
    assert int(output_lines["count"]) == len(all_dockerfiles)
    matrix = json.loads(output_lines["matrix"])
    assert len(matrix["include"]) == len(all_dockerfiles)

    summary = step_summary.read_text(encoding="utf-8")
    plan = select_harness_build_plan(
        ["src/clawbench/runtime/runtime-server/server.py"],
        event_name="pull_request",
        repo_root=REPO_ROOT,
    )
    assert summary == format_harness_build_summary("pull_request", plan)
    assert "- Event: `pull_request`" in summary
    assert "- Selection mode: `all`" in summary
    assert f"- Harness images: `{len(all_dockerfiles)}`" in summary
    for harness in HARNESS_REGISTRY.harnesses:
        assert f"| `clawbench-{harness}` |" in summary


def test_check_harness_build_workflow_uses_shared_selector() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "clawbench.runner.run_support.harness_build_plan" in workflow_text
    assert "extension-server/" not in workflow_text
