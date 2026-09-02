"""CI must see both corpus layouts, not just <suite>/<case>/task.json.

The claw-eval suite is a first-class `--cases-suite` target and is offered in
the TUI, but it stores one flat `<suite>/<id>.json` per task. The validate-task
workflow's path filter (`test-cases/**/task.json`) never matched those files,
so a PR touching a claw-eval task was merged with no schema validation at all.

Fixing the trigger alone was not enough: the collector only recognised files
named `task.json`, so even once the workflow fired it validated nothing from
that suite. Both halves are covered here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "validate-task.yml"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import validate_tasks as vt  # noqa: E402


# --- the layouts the collector must recognise ---------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "test-cases/claw-eval/ce-T046-cve-research.json",
        "test-cases/claw-eval/ce-T045zh-cve-research.json",
    ],
)
def test_a_flat_suite_file_is_a_task(path: str) -> None:
    assert vt.is_flat_task(Path(path))
    assert vt.is_task_file(Path(path))


def test_a_directory_style_task_is_still_a_task() -> None:
    path = Path("test-cases/v2/002-daily-life-food-doordash/task.json")
    assert vt.is_nested_task(path)
    assert vt.is_task_file(path)
    assert not vt.is_flat_task(path)


@pytest.mark.parametrize(
    "path",
    [
        "test-cases/task.schema.json",  # the schema, not a task
        "test-cases/claw-eval/eligibility-report.json",  # a report
        "test-cases/v2/002-x/extra_info/menu.json",  # task payload, not a task
        "test-cases/v2/002-x/task.md",  # not JSON
        "docs/scoring.md",  # outside the corpus
    ],
)
def test_non_task_json_is_not_collected_as_a_task(path: str) -> None:
    """Broadening the trigger to *.json must not turn every file into a task."""
    assert not vt.is_task_file(Path(path))


def test_the_flat_predicate_matches_the_runners_own_rule() -> None:
    """batch._flat_case_files and tests/test_host_tasks both treat every
    <suite>/*.json except eligibility-report.json as a case; the validator must
    agree, or CI checks a different set of files than the runner executes."""
    from clawbench.runner.batch import _flat_case_files

    base = REPO_ROOT / "test-cases" / "claw-eval"
    runner_view = {p.name for p in _flat_case_files(base)}
    validator_view = {
        p.name
        for p in base.glob("*.json")
        if vt.is_flat_task(Path("test-cases/claw-eval") / p.name)
    }

    assert runner_view == validator_view
    assert runner_view, "claw-eval should not be empty"


# --- collection ---------------------------------------------------------------


def test_a_changed_flat_task_is_validated(tmp_path: Path) -> None:
    """The regression: this file used to be collected by nothing."""
    suite = tmp_path / "test-cases" / "claw-eval"
    suite.mkdir(parents=True)
    (suite / "ce-T046.json").write_text("{}")

    task_files, changed_json = vt.collect(
        [Path("test-cases/claw-eval/ce-T046.json")], tmp_path
    )

    assert task_files == {Path("test-cases/claw-eval/ce-T046.json")}
    assert changed_json == task_files


def test_a_changed_nested_task_is_validated(tmp_path: Path) -> None:
    case = tmp_path / "test-cases" / "v2" / "002-x"
    case.mkdir(parents=True)
    (case / "task.json").write_text("{}")

    task_files, _ = vt.collect([Path("test-cases/v2/002-x/task.json")], tmp_path)

    assert task_files == {Path("test-cases/v2/002-x/task.json")}


def test_changed_extra_info_pulls_in_its_owning_task(tmp_path: Path) -> None:
    case = tmp_path / "test-cases" / "v2" / "002-x"
    (case / "extra_info").mkdir(parents=True)
    (case / "task.json").write_text("{}")
    (case / "extra_info" / "menu.json").write_text("{}")

    task_files, changed_json = vt.collect(
        [Path("test-cases/v2/002-x/extra_info/menu.json")], tmp_path
    )

    assert task_files == {Path("test-cases/v2/002-x/task.json")}
    assert changed_json == {Path("test-cases/v2/002-x/extra_info/menu.json")}


def test_a_schema_change_revalidates_both_layouts(tmp_path: Path) -> None:
    """A schema edit has to re-check the flat suite too, or claw-eval drifts
    out of conformance the moment the schema tightens."""
    root = tmp_path / "test-cases"
    (root / "v2" / "002-x").mkdir(parents=True)
    (root / "claw-eval").mkdir(parents=True)
    (root / "v2" / "002-x" / "task.json").write_text("{}")
    (root / "claw-eval" / "ce-T046.json").write_text("{}")
    (root / "task.schema.json").write_text("{}")

    task_files, _ = vt.collect([vt.SCHEMA_PATH], tmp_path)

    assert task_files == {
        Path("test-cases/v2/002-x/task.json"),
        Path("test-cases/claw-eval/ce-T046.json"),
    }


def test_a_deleted_task_is_not_validated(tmp_path: Path) -> None:
    """git diff lists deletions; there is nothing left to read."""
    (tmp_path / "test-cases" / "claw-eval").mkdir(parents=True)

    task_files, changed_json = vt.collect(
        [Path("test-cases/claw-eval/gone.json")], tmp_path
    )

    assert task_files == set()
    assert changed_json == set()


# --- validation ---------------------------------------------------------------


def test_a_malformed_flat_task_is_reported(tmp_path: Path) -> None:
    """The point of the whole workflow: this must fail review, not run time."""
    root = tmp_path / "test-cases"
    (root / "claw-eval").mkdir(parents=True)
    (root / "task.schema.json").write_text(
        json.dumps({"type": "object", "required": ["instruction"]})
    )
    bad = root / "claw-eval" / "ce-T046.json"
    bad.write_text(json.dumps({"time_limit": 10}))

    errors = vt.validate({Path("test-cases/claw-eval/ce-T046.json")}, set(), tmp_path)

    assert len(errors) == 1
    assert "instruction" in errors[0]


def test_the_real_claw_eval_suite_validates() -> None:
    """Turning the check on must not immediately break CI."""
    flat = {p for p in vt.all_task_files(REPO_ROOT) if vt.is_flat_task(p)}

    assert len(flat) == 19, flat
    assert vt.validate(flat, set(), REPO_ROOT) == []


# --- the workflow trigger -----------------------------------------------------


def _trigger_paths(event: str) -> list[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # "on" is parsed as the boolean True by YAML 1.1.
    triggers = workflow.get("on") or workflow[True]
    return triggers[event]["paths"]


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_the_workflow_fires_for_flat_suite_files(event: str) -> None:
    """The original bug was entirely in this filter: `test-cases/**/task.json`
    cannot match `test-cases/claw-eval/ce-T046-cve-research.json`."""
    paths = _trigger_paths(event)

    assert "test-cases/**/*.json" in paths
    assert "test-cases/**/task.json" not in paths


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_the_workflow_reruns_when_the_validator_itself_changes(event: str) -> None:
    assert "scripts/ci/validate_tasks.py" in _trigger_paths(event)
