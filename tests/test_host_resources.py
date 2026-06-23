"""Tests for host-side resources prepared before container startup."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from clawbench.runner.run_support.task import (
    build_instruction,
    copy_extra_info,
    normalize_extra_info,
    prepare_personal_info,
)
from clawbench.utils.paths import ASSET_ROOT, SHARED_ROOT

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = REPO_ROOT / "src" / "clawbench" / "runtime"


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


def test_harnesses_use_shared_browser_cdp_env() -> None:
    forbidden = "http://127.0.0.1:9222"
    allowed = {
        RUNTIME_ROOT / "harnesses" / "base" / "entrypoint.sh",
    }

    offenders = []
    for path in (RUNTIME_ROOT / "harnesses").rglob("*"):
        if not path.is_file() or path in allowed:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if forbidden in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []


def test_harnesses_are_browser_provider_neutral() -> None:
    forbidden = ("STEEL", "BROWSERBASE", "steel", "browserbase")
    offenders = []
    for path in (RUNTIME_ROOT / "harnesses").rglob("*"):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(token in text for token in forbidden):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == []


def test_runtime_server_cdp_url_comes_from_env_with_local_default() -> None:
    server_path = RUNTIME_ROOT / "runtime-server" / "server.py"
    tree = ast.parse(server_path.read_text(encoding="utf-8"))

    cdp_assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CDP_URL"
            for target in node.targets
        )
    ]

    assert len(cdp_assignments) == 1
    value = cdp_assignments[0].value
    assert isinstance(value, ast.Call)
    assert isinstance(value.func, ast.Attribute)
    assert value.func.attr == "get"
    assert isinstance(value.func.value, ast.Attribute)
    assert value.func.value.attr == "environ"
    assert isinstance(value.func.value.value, ast.Name)
    assert value.func.value.value.id == "os"
    assert [arg.value for arg in value.args if isinstance(arg, ast.Constant)] == [
        "CLAWBENCH_BROWSER_CDP_URL",
        "http://127.0.0.1:9222",
    ]
