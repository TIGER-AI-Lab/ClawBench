#!/usr/bin/env python3
"""Validate ClawBench task files against test-cases/task.schema.json.

Two corpus layouts exist and both are first-class:

- v1 / v2 / v1-lite keep one directory per task, holding a `task.json`.
- claw-eval keeps one flat `<suite>/<id>.json` per task.

A validator that only knows about `task.json` silently ignores the whole
claw-eval suite, which is registered in `CASE_SUITES` and offered in the TUI,
so a malformed task there surfaces at run time instead of at review time.

Lives in a script rather than inline in the workflow so the collection rules
can be tested; that is what let the gap go unnoticed in the first place.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

TEST_CASES = "test-cases"
SCHEMA_PATH = Path(TEST_CASES) / "task.schema.json"

# JSON under test-cases/ that is not a task document.
NOT_TASKS = {"task.schema.json", "eligibility-report.json"}


def is_nested_task(path: Path) -> bool:
    """`test-cases/<suite>/<case>/task.json` — the v1/v2/v1-lite layout."""
    return path.parts[:1] == (TEST_CASES,) and path.name == "task.json"


def is_flat_task(path: Path) -> bool:
    """`test-cases/<suite>/<id>.json` — the claw-eval layout."""
    return (
        path.parts[:1] == (TEST_CASES,)
        and len(path.parts) == 3
        and path.suffix == ".json"
        and path.name not in NOT_TASKS
        and "extra_info" not in path.parts
    )


def is_task_file(path: Path) -> bool:
    return is_nested_task(path) or is_flat_task(path)


def all_task_files(repo: Path) -> set[Path]:
    """Every task document in the corpus, in either layout."""
    found = {p.relative_to(repo) for p in repo.glob(f"{TEST_CASES}/**/task.json")}
    found |= {
        p.relative_to(repo)
        for p in repo.glob(f"{TEST_CASES}/*/*.json")
        if is_flat_task(p.relative_to(repo))
    }
    return found


def collect(changed_paths: list[Path], repo: Path) -> tuple[set[Path], set[Path]]:
    """Return (task files to validate, changed JSON files to parse-check).

    A change to the schema itself re-validates the whole corpus; otherwise only
    what the diff touched, plus the owning task of any changed `extra_info`.
    """
    task_files: set[Path] = set()
    changed_json: set[Path] = set()

    if SCHEMA_PATH in changed_paths:
        task_files |= all_task_files(repo)

    for path in changed_paths:
        if path.parts[:1] != (TEST_CASES,):
            continue
        if is_task_file(path) and (repo / path).exists():
            task_files.add(path)
            changed_json.add(path)
            continue
        if "extra_info" in path.parts:
            extra_index = path.parts.index("extra_info")
            owner = Path(*path.parts[:extra_index]) / "task.json"
            if (repo / owner).exists():
                task_files.add(owner)
            if path.suffix == ".json" and (repo / path).exists():
                changed_json.add(path)

    return task_files, changed_json


def validate(task_files: set[Path], changed_json: set[Path], repo: Path) -> list[str]:
    schema = json.loads((repo / SCHEMA_PATH).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    errors: list[str] = []

    for json_file in sorted(changed_json):
        try:
            json.loads((repo / json_file).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — reported, not handled
            errors.append(f"{json_file}: invalid JSON: {exc}")

    for task_file in sorted(task_files):
        try:
            task = json.loads((repo / task_file).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 — reported, not handled
            errors.append(f"{task_file}: invalid JSON: {exc}")
            continue

        for error in sorted(validator.iter_errors(task), key=lambda e: list(e.path)):
            location = "/" + "/".join(str(part) for part in error.path)
            errors.append(f"{task_file}{location}: {error.message}")

        extra_info = task.get("extra_info") or []
        if not isinstance(extra_info, list):
            continue
        for index, item in enumerate(extra_info):
            if not isinstance(item, dict) or not item.get("path"):
                continue
            if not (repo / task_file.parent / item["path"]).exists():
                errors.append(
                    f"{task_file}: extra_info[{index}].path does not exist: "
                    f"{item['path']}"
                )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-files",
        type=Path,
        help="File listing changed paths, one per line (from git diff --name-only).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate the whole corpus regardless of what changed.",
    )
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    repo = args.repo
    if args.all or not args.changed_files:
        task_files = all_task_files(repo)
        changed_json: set[Path] = set()
    else:
        changed_paths = [
            Path(line.strip())
            for line in args.changed_files.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        task_files, changed_json = collect(changed_paths, repo)

    errors = validate(task_files, changed_json, repo)
    if errors:
        print("Task validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"Validated {len(task_files)} task file(s) and "
        f"{len(changed_json)} changed JSON file(s)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
