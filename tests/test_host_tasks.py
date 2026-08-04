"""Task discovery and validation tests that use only Python filesystem APIs."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from clawbench.runner import batch
from clawbench.runner.run_support.task import validate_task_data
from clawbench.utils.paths import ASSET_ROOT


def _suite_base(suite: str) -> Path:
    return ASSET_ROOT / batch.CASE_SUITES[suite]


def _task_files_for_suite(suite: str) -> list[Path]:
    base = _suite_base(suite)
    task_files = [path for path in base.glob("*/task.json") if path.is_file()]
    task_files.extend(
        path
        for path in base.glob("*.json")
        if path.is_file() and path.name != "eligibility-report.json"
    )
    return sorted(task_files)


@pytest.mark.parametrize("suite", sorted(batch.CASE_SUITES))
def test_builtin_case_suites_are_discoverable(suite: str) -> None:
    cases = batch.discover_cases(
        patterns=None,
        all_cases=True,
        cases_dir=batch.CASE_SUITES[suite],
    )

    assert cases, f"{suite} should contain at least one case"
    for case in cases:
        if case.is_dir():
            assert (case / "task.json").is_file()
        else:
            assert case.is_file()


@pytest.mark.parametrize("suite", sorted(batch.CASE_SUITES))
def test_checked_task_json_files_parse_and_validate(suite: str) -> None:
    task_files = _task_files_for_suite(suite)

    assert task_files, f"{suite} should expose readable task JSON files"
    for task_file in task_files:
        task = json.loads(task_file.read_bytes())
        validated = validate_task_data(task, task_file)
        assert validated is task


@pytest.mark.parametrize("suite", sorted(batch.CASE_SUITES))
def test_task_url_patterns_are_nonempty_and_valid_regex(suite: str) -> None:
    """validate_task_data only checks url_pattern is a *string* — an empty pattern
    (re.search('', url) matches everything → false positives) or a malformed regex
    (interceptor crashes at runtime) still slips through. Guard against both."""
    for task_file in _task_files_for_suite(suite):
        task = json.loads(task_file.read_bytes())
        pattern = task["eval_schema"]["url_pattern"]
        assert pattern.strip(), (
            f"{task_file}: eval_schema.url_pattern is empty — would match every "
            f"request (false-positive interceptions)"
        )
        try:
            re.compile(pattern)
        except re.error as exc:  # malformed regex would crash the interceptor
            raise AssertionError(
                f"{task_file}: url_pattern is not valid regex: {exc}"
            ) from exc


@pytest.mark.parametrize("suite", sorted(batch.CASE_SUITES))
def test_tasks_are_not_duplicated(suite: str) -> None:
    """No two tasks share the same target + instruction (accidental copy-paste)."""
    seen: dict[tuple[str, str, str], str] = {}
    for task_file in _task_files_for_suite(suite):
        task = json.loads(task_file.read_bytes())
        schema = task["eval_schema"]
        key = (
            schema["url_pattern"],
            str(schema.get("method", "")),
            str(task["instruction"]).strip(),
        )
        prev = seen.get(key)
        assert prev is None, (
            f"duplicate task in {suite}: {task_file.parent.name} == {prev}"
        )
        seen[key] = task_file.parent.name


def test_v1_lite_linked_files_are_readable_from_python() -> None:
    base = _suite_base("v1-lite")
    linked_files = [
        *base.glob("*/task.json"),
        *base.glob("*/extra_info/*"),
    ]

    assert linked_files, "v1-lite should contain task and extra_info files"
    for path in linked_files:
        assert path.is_file(), f"{path} should resolve to a readable file"
        assert path.read_bytes(), f"{path} should not be empty"
