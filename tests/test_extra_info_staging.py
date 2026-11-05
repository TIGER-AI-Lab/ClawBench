"""Tests for native extra_info collision preflight and staging safety."""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from clawbench.runner.run_support.task import (
    RESERVED_PERSONAL_INFO_FILES,
    build_instruction,
    copy_extra_info,
    prepare_personal_info,
    validate_task_data,
)
from clawbench.utils.paths import SHARED_ROOT


def _base_task(extra_info: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "instruction": "Use the reference files.",
        "eval_schema": {
            "url_pattern": "https://example\\.test/submit",
            "method": "POST",
        },
        "time_limit": 5,
        "extra_info": extra_info,
    }


def _import_run_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    for module_name in (
        "clawbench.runner.run",
        "clawbench.runner.run_support.metadata",
        "clawbench.runner.run_support.docker",
        "clawbench.runner.run_support.config",
    ):
        sys.modules.pop(module_name, None)
    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda cmd: str(Path("mock-bin") / cmd) if cmd == "docker" else None,
    )
    return importlib.import_module("clawbench.runner.run")


def test_copy_extra_info_rejects_issue_409_reproduction_without_side_effects(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "case"
    (task_dir / "a").mkdir(parents=True)
    (task_dir / "b").mkdir(parents=True)
    (task_dir / "a" / "reference.txt").write_text("first", encoding="utf-8")
    (task_dir / "b" / "reference.txt").write_text("second", encoding="utf-8")
    (task_dir / "a" / "email_credentials.json").write_text(
        "overwrite", encoding="utf-8"
    )

    my_info = tmp_path / "my-info"
    my_info.mkdir()
    (my_info / "email_credentials.json").write_text("generated-creds", encoding="utf-8")

    task = _base_task(
        [
            {"path": "a/reference.txt", "description": "first ref"},
            {"path": "b/reference.txt", "description": "second ref"},
            {"path": "a/email_credentials.json", "description": "bad name"},
        ]
    )

    with pytest.raises(ValueError, match="basename collision"):
        copy_extra_info(task, task_dir, my_info)

    assert (my_info / "email_credentials.json").read_text(encoding="utf-8") == (
        "generated-creds"
    )
    assert not (my_info / "reference.txt").exists()


def test_duplicate_basenames_leave_existing_generated_and_staged_files_unchanged(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "case"
    (task_dir / "a").mkdir(parents=True)
    (task_dir / "b").mkdir(parents=True)
    (task_dir / "a" / "first_ok.txt").write_text(
        "should not be staged", encoding="utf-8"
    )
    (task_dir / "a" / "reference.txt").write_text("first", encoding="utf-8")
    (task_dir / "b" / "reference.txt").write_text("second", encoding="utf-8")

    info_dir, _ = prepare_personal_info(
        SHARED_ROOT,
        "alex@example.test",
        "secret-password",
        tmp_path,
    )
    (info_dir / "prior_attachment.txt").write_text("keep me", encoding="utf-8")
    before_snapshots = {
        path.name: path.read_bytes() for path in info_dir.iterdir() if path.is_file()
    }

    task = _base_task(
        [
            {"path": "a/first_ok.txt", "description": "valid first entry"},
            {"path": "a/reference.txt", "description": "first ref"},
            {"path": "b/reference.txt", "description": "second ref"},
        ]
    )

    with pytest.raises(
        ValueError,
        match=(
            r"extra_info basename collision: "
            r"'a/reference\.txt' and 'b/reference\.txt' both map to 'reference\.txt'"
        ),
    ):
        copy_extra_info(task, task_dir, info_dir)

    with pytest.raises(ValueError, match="basename collision"):
        build_instruction(task)

    with pytest.raises(ValueError, match="basename collision"):
        validate_task_data(task, task_dir / "task.json")

    after_snapshots = {
        path.name: path.read_bytes() for path in info_dir.iterdir() if path.is_file()
    }
    assert after_snapshots == before_snapshots


@pytest.mark.parametrize("reserved_name", sorted(RESERVED_PERSONAL_INFO_FILES))
def test_reserved_personal_info_filenames_are_rejected_before_overwrite(
    tmp_path: Path, reserved_name: str
) -> None:
    task_dir = tmp_path / "case"
    (task_dir / "sub").mkdir(parents=True)
    (task_dir / "sub" / "notes.txt").write_text("notes", encoding="utf-8")
    (task_dir / "sub" / reserved_name).write_text(
        "malicious-overwrite", encoding="utf-8"
    )

    my_info = tmp_path / "my-info"
    my_info.mkdir()
    (my_info / reserved_name).write_text("original-generated-content", encoding="utf-8")

    task = _base_task(
        [
            {"path": "sub/notes.txt", "description": "valid attachment"},
            {"path": f"sub/{reserved_name}", "description": "collides with reserved"},
        ]
    )

    with pytest.raises(ValueError, match="reserved personal-info file"):
        copy_extra_info(task, task_dir, my_info)

    assert (my_info / reserved_name).read_text(encoding="utf-8") == (
        "original-generated-content"
    )
    assert not (my_info / "notes.txt").exists()

    with pytest.raises(ValueError, match="reserved personal-info file"):
        build_instruction(task)

    with pytest.raises(ValueError, match="reserved personal-info file"):
        validate_task_data(task, task_dir / "task.json")


def test_existing_staged_attachment_collision_leaves_directory_unchanged(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "case"
    (task_dir / "sub").mkdir(parents=True)
    (task_dir / "sub" / "fresh.txt").write_text("fresh", encoding="utf-8")
    (task_dir / "sub" / "existing.txt").write_text("new-content", encoding="utf-8")

    my_info = tmp_path / "my-info"
    my_info.mkdir()
    (my_info / "existing.txt").write_text("already-staged", encoding="utf-8")

    task = _base_task(
        [
            {"path": "sub/fresh.txt", "description": "fresh attachment"},
            {"path": "sub/existing.txt", "description": "collides with existing"},
        ]
    )

    with pytest.raises(ValueError, match="existing personal-info file"):
        copy_extra_info(task, task_dir, my_info)

    assert (my_info / "existing.txt").read_text(encoding="utf-8") == "already-staged"
    assert not (my_info / "fresh.txt").exists()


def test_ordinary_distinct_attachments_stage_and_match_instruction(
    tmp_path: Path,
) -> None:
    task_dir = tmp_path / "case"
    (task_dir / "a").mkdir(parents=True)
    (task_dir / "b").mkdir(parents=True)
    (task_dir / "a" / "first_ref.txt").write_text("first", encoding="utf-8")
    (task_dir / "b" / "second_ref.json").write_text('{"ok": true}', encoding="utf-8")

    my_info = tmp_path / "my-info"
    my_info.mkdir()

    task = _base_task(
        [
            {"path": "a/first_ref.txt", "description": "First reference"},
            {"path": "b/second_ref.json", "description": "Second reference"},
        ]
    )

    validated = validate_task_data(task, task_dir / "task.json")
    assert validated is task

    warnings = copy_extra_info(task, task_dir, my_info)
    instruction = build_instruction(task)

    assert warnings == []
    assert (my_info / "first_ref.txt").read_text(encoding="utf-8") == "first"
    assert (my_info / "second_ref.json").read_text(encoding="utf-8") == '{"ok": true}'
    assert "- first_ref.txt: First reference" in instruction
    assert "- second_ref.json: Second reference" in instruction


def test_native_run_reports_extra_info_collision_as_task_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    run_mod = _import_run_module(monkeypatch)

    task_dir = tmp_path / "case"
    (task_dir / "a").mkdir(parents=True)
    (task_dir / "b").mkdir(parents=True)
    (task_dir / "a" / "reference.txt").write_text("first", encoding="utf-8")
    (task_dir / "b" / "reference.txt").write_text("second", encoding="utf-8")
    task = _base_task(
        [
            {"path": "a/reference.txt", "description": "first ref"},
            {"path": "b/reference.txt", "description": "second ref"},
        ]
    )
    (task_dir / "task.json").write_text(json.dumps(task), encoding="utf-8")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        run_mod.sys,
        "argv",
        [
            "clawbench-run",
            str(task_dir),
            "model-a",
            "--no-build",
            "--no-upload",
            "--no-judge",
            "--output-dir",
            str(output_dir),
        ],
    )
    monkeypatch.setattr(run_mod, "ensure_workspace_templates", lambda: None)
    monkeypatch.setattr(
        run_mod,
        "load_runtime_env",
        lambda: {
            "PURELY_MAIL_API_KEY": "pm-key",
            "PURELY_MAIL_DOMAIN": "example.test",
        },
    )
    monkeypatch.setattr(
        run_mod,
        "load_model_config",
        lambda model: {
            "model": model,
            "base_url": "https://api.example.test/v1",
            "api_type": "openai-completions",
            "api_key": "secret-key",
            "api_keys": ["secret-key"],
        },
    )

    class _FakeProvider:
        name = "local"
        mode = "local"

    monkeypatch.setattr(
        run_mod, "make_browser_runtime_provider", lambda _args, _env: _FakeProvider()
    )

    docker_calls: list[str] = []
    monkeypatch.setattr(
        run_mod, "docker_run", lambda *_args, **_kwargs: docker_calls.append("run")
    )
    written: list[tuple[Path, dict[str, Any]]] = []
    monkeypatch.setattr(
        run_mod,
        "make_run_meta",
        lambda **kwargs: {
            "failure_reason": kwargs.get("failure_reason"),
            "classification": kwargs.get("classification"),
        },
    )
    monkeypatch.setattr(
        run_mod,
        "write_run_meta",
        lambda out, meta: written.append((out, meta)),
    )

    with pytest.raises(SystemExit) as excinfo:
        run_mod.main()

    assert excinfo.value.code == 2
    assert docker_calls == []
    assert len(written) == 1
    meta = written[0][1]
    assert meta["failure_reason"].startswith("task_data: ")
    assert "basename collision" in meta["failure_reason"]
    assert meta["classification"]["failure_category"] == "task_data"
