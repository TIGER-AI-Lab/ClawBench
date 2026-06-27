"""Tests for host-side resources prepared before container startup."""

from __future__ import annotations

import json
from pathlib import Path

from clawbench.runner.run_support.task import (
    build_instruction,
    copy_extra_info,
    normalize_extra_info,
    prepare_personal_info,
)
from clawbench.utils.paths import ASSET_ROOT, SHARED_ROOT


def test_prepare_personal_info_writes_container_mount_resources(tmp_path: Path) -> None:
    info_dir, metadata = prepare_personal_info(
        SHARED_ROOT,
        "alex@example.test",
        "correct-horse-battery-staple",
        tmp_path,
    )

    personal_info = json.loads(
        (info_dir / "alex_green_personal_info.json").read_text(encoding="utf-8")
    )
    email_credentials = json.loads(
        (info_dir / "email_credentials.json").read_text(encoding="utf-8")
    )

    assert personal_info["contact"]["email"] == "alex@example.test"
    assert "online_accounts" not in personal_info
    assert email_credentials == {
        "email": "alex@example.test",
        "password": "correct-horse-battery-staple",
        "login_url": "https://purelymail.com/user/login",
        "provider": "PurelyMail",
    }
    assert (info_dir / "alex_green_resume.pdf").is_file()
    assert metadata["personal_info_source_json_sha256"]
    assert metadata["resume_pdf_source_json_sha256"]


def test_extra_info_copy_and_instruction_are_host_side(tmp_path: Path) -> None:
    task_dir = ASSET_ROOT / "test-cases" / "v1" / "007-daily-life-food-instacart"
    task = json.loads((task_dir / "task.json").read_bytes())
    my_info = tmp_path / "my-info"
    my_info.mkdir()

    warnings = copy_extra_info(task, task_dir, my_info)
    instruction = build_instruction(task)

    assert warnings == []
    assert (my_info / "meal_plan.json").is_file()
    assert "On Instacart" in instruction
    assert "Do NOT use command-line tools" in instruction
    assert "meal_plan.json" in instruction
    assert "2-day meal plan" in instruction


def test_build_instruction_lists_only_available_builtin_files() -> None:
    # The default lists all built-in my-info files; passing a subset (as the Harbor
    # exporter does when a built-in can't be staged) drops the rest from the prompt
    # so it never references a file that is missing from /my-info/.
    task = {"instruction": "Do a thing.", "extra_info": []}
    full = build_instruction(task)
    assert "alex_green_personal_info.json" in full
    assert "email_credentials.json" in full
    assert "alex_green_resume.pdf" in full

    subset = build_instruction(
        task, builtin_files=[("alex_green_personal_info.json", "info")]
    )
    assert "alex_green_personal_info.json" in subset
    assert "email_credentials.json" not in subset
    assert "alex_green_resume.pdf" not in subset


def test_normalize_extra_info_accepts_legacy_and_schema_shapes() -> None:
    entries, warnings = normalize_extra_info(
        [
            "plain note",
            {"path": "extra_info/data.json", "description": "structured file"},
            {"content": {"nested": True}},
            42,
            object(),
        ]
    )

    assert entries[:4] == [
        {"description": "plain note"},
        {"path": "extra_info/data.json", "description": "structured file"},
        {"description": '{"nested": true}'},
        {"description": "42"},
    ]
    assert len(warnings) == 1
    assert "unsupported type" in warnings[0]
