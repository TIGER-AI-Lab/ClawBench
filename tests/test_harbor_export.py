"""Tests for clawbench.harbor.export (ClawBench task.json -> Harbor task dir)."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from clawbench.harbor import export


def _write_case(
    parent: Path,
    name: str,
    *,
    instruction: str = "Add Baked Ziti to Want to Try collection on MyRecipes",
    cls: str = "collection",
    time_limit: int = 30,
) -> Path:
    case = parent / name
    case.mkdir(parents=True)
    task = {
        "metadata": {
            "task_id": 1100,
            "metaclass": "food-cooking",
            "class": cls,
            "description": "Add Baked Ziti to Want to Try collection on MyRecipes",
            "platform": "myrecipes",
        },
        "instruction": instruction,
        "eval_schema": {
            "url_pattern": "myrecipes\\.com/collections/bookmarks/save",
            "method": "POST",
        },
        "time_limit": time_limit,
        "extra_info": [],
    }
    (case / "task.json").write_text(json.dumps(task, indent=2))
    return case


def test_export_case_produces_harbor_task_dir(tmp_path: Path) -> None:
    case = _write_case(tmp_path / "v2", "v2-1100-food-cooking-collection-myrecipes")
    out = tmp_path / "out"
    out.mkdir()
    ok, msg = export.export_case(
        case,
        out,
        base_image="localhost/clawbench-harbor-task:latest",
        no_judge=True,
        judge_env={},
    )
    assert ok, msg
    dst = out / case.name

    # Canonical Harbor files exist. PREBUILT mode: docker-compose.yaml, NO Dockerfile.
    assert (dst / "task.toml").is_file()
    assert (dst / "instruction.md").is_file()
    assert (dst / "environment" / "docker-compose.yaml").is_file()
    assert not (dst / "environment" / "Dockerfile").exists()
    assert (dst / "environment" / "eval-schema.json").is_file()
    assert (dst / "environment" / "instruction.txt").is_file()
    assert (dst / "tests" / "test.sh").is_file()

    # task.toml parses and carries the expected sections/metadata.
    cfg = tomllib.loads((dst / "task.toml").read_text())
    assert cfg["version"] == "1.0"
    assert cfg["task"]["name"].startswith("clawbench/")
    assert cfg["metadata"]["clawbench_case"] == case.name
    assert cfg["metadata"]["clawbench_no_judge"] is True
    assert cfg["metadata"]["clawbench_platform"] == "myrecipes"
    # eval schema is round-trippable JSON baked into metadata.
    schema = json.loads(cfg["metadata"]["clawbench_eval_schema"])
    assert schema["method"] == "POST"
    assert "agent" in cfg and "verifier" in cfg and "environment" in cfg
    assert cfg["agent"]["timeout_sec"] == float(time_limit_s := 30 * 60)
    assert cfg["verifier"]["timeout_sec"] >= time_limit_s
    # PREBUILT mode: [environment].docker_image points at the local image -> Harbor
    # uses docker-compose-prebuilt.yaml (no build).
    assert (
        cfg["environment"]["docker_image"] == "localhost/clawbench-harbor-task:latest"
    )

    # eval-schema.json baked verbatim.
    baked = json.loads((dst / "environment" / "eval-schema.json").read_text())
    assert baked["url_pattern"] == "myrecipes\\.com/collections/bookmarks/save"

    # docker-compose.yaml delivers the per-task files via bind mounts (no build).
    compose = (dst / "environment" / "docker-compose.yaml").read_text()
    assert "./eval-schema.json:/eval-schema.json:ro" in compose
    assert "./instruction.txt:/clawbench/instruction.txt:ro" in compose
    assert "./my-info:/clawbench/my-info:ro" in compose
    assert "pull_policy: never" in compose

    # test.sh runs the verifier shim and falls back to a 0.0 reward in BOTH the
    # canonical reward.json and the reward.txt fallback (M1).
    test_sh = (dst / "tests" / "test.sh").read_text()
    assert "python3 -m clawbench.harbor.verify" in test_sh
    assert "/logs/verifier/reward.json" in test_sh
    assert "/logs/verifier/reward.txt" in test_sh
    # --no-judge requested -> flag is present.
    assert "--no-judge" in test_sh

    # Persona is copied into the bind-mounted my-info dir.
    assert (dst / "environment" / "my-info" / "alex_green_personal_info.json").is_file()


def test_export_with_judge_bakes_verifier_env(tmp_path: Path) -> None:
    case = _write_case(tmp_path / "v2", "v2-1100-food-cooking-collection-myrecipes")
    out = tmp_path / "out"
    out.mkdir()
    judge_env = {
        "JUDGE_MODEL": "gemini-3.5-flash",
        "JUDGE_BASE_URL": "https://generativelanguage.googleapis.com/v1beta/openai",
        "JUDGE_API_TYPE": "openai-completions",
        "JUDGE_API_KEY": "secret",
    }
    ok, _ = export.export_case(
        case,
        out,
        base_image="clawbench-harbor-task",
        no_judge=False,
        judge_env=judge_env,
    )
    assert ok
    task_toml_text = (out / case.name / "task.toml").read_text()
    cfg = tomllib.loads(task_toml_text)
    # Non-secret judge config IS baked into [verifier.env].
    assert cfg["verifier"]["env"]["JUDGE_MODEL"] == "gemini-3.5-flash"
    assert cfg["verifier"]["env"]["JUDGE_API_TYPE"] == "openai-completions"
    # C1 / m1(b): the judge API key must NEVER be baked into the shareable task.toml
    # (it is injected at runtime via `harbor run --ve JUDGE_API_KEY=...`).
    assert "JUDGE_API_KEY" not in cfg["verifier"]["env"]
    assert "JUDGE_API_KEY" not in task_toml_text
    assert "secret" not in task_toml_text
    # test.sh should NOT carry --no-judge when judging is on.
    test_sh = (out / case.name / "tests" / "test.sh").read_text()
    assert "--no-judge" not in test_sh


def test_export_copies_all_extra_info_into_my_info(tmp_path: Path) -> None:
    # M4: every extra_info file the task references must land in environment/my-info
    # so build_instruction()'s /my-info/ file list never points at a missing file.
    case = _write_case(tmp_path / "v2", "v2-extra")
    task = json.loads((case / "task.json").read_text())
    (case / "extra_info").mkdir()
    (case / "extra_info" / "address_info.json").write_text('{"city": "Vancouver"}')
    task["extra_info"] = [
        {"path": "extra_info/address_info.json", "description": "Address info"}
    ]
    (case / "task.json").write_text(json.dumps(task, indent=2))

    out = tmp_path / "out"
    out.mkdir()
    ok, msg = export.export_case(
        case,
        out,
        base_image="localhost/clawbench-harbor-task:latest",
        no_judge=True,
        judge_env={},
    )
    assert ok, msg
    my_info = out / case.name / "environment" / "my-info"
    assert (my_info / "alex_green_personal_info.json").is_file()
    assert (my_info / "address_info.json").is_file()
    # The exported instruction references the copied file by name.
    instruction = (out / case.name / "instruction.md").read_text()
    assert "address_info.json" in instruction


def test_export_fails_when_referenced_extra_info_file_missing(tmp_path: Path) -> None:
    # M4: copy_extra_info only warns on a missing file, but build_instruction()
    # still advertises it under /my-info/. Export must FAIL rather than ship an
    # instruction that points at a non-existent file.
    case = _write_case(tmp_path / "v2", "v2-missing-extra")
    task = json.loads((case / "task.json").read_text())
    task["extra_info"] = [
        {"path": "extra_info/nope.json", "description": "A file that does not exist"}
    ]
    (case / "task.json").write_text(json.dumps(task, indent=2))
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(RuntimeError, match="missing from my-info"):
        export.export_case(case, out, base_image="x", no_judge=True, judge_env={})
    # Nothing partial is shipped for the failed case.
    assert not (out / case.name).exists()


def test_task_toml_escapes_multiline_and_control_chars(tmp_path: Path) -> None:
    # _toml_escape must handle newlines/tabs/control chars so a multiline
    # description still yields parseable TOML.
    case = _write_case(tmp_path / "v2", "v2-multiline")
    task = json.loads((case / "task.json").read_text())
    weird = 'Line one\nLine two\tTabbed\r\nQuote " and back\\slash\x07bell'
    task["metadata"]["description"] = weird
    (case / "task.json").write_text(json.dumps(task, indent=2))
    out = tmp_path / "out"
    out.mkdir()
    ok, msg = export.export_case(case, out, base_image="x", no_judge=True, judge_env={})
    assert ok, msg
    text = (out / case.name / "task.toml").read_text()
    # Must parse, and the description must round-trip exactly.
    cfg = tomllib.loads(text)
    assert cfg["task"]["description"] == weird


def test_registration_class_is_skipped(tmp_path: Path) -> None:
    case = _write_case(tmp_path / "v2", "v2-signup", cls="registration")
    out = tmp_path / "out"
    out.mkdir()
    ok, msg = export.export_case(case, out, base_image="x", no_judge=True, judge_env={})
    assert not ok
    assert "SKIP" in msg
    assert not (out / case.name).exists()


def test_email_verification_instruction_is_skipped(tmp_path: Path) -> None:
    case = _write_case(
        tmp_path / "v2",
        "v2-email",
        cls="general",
        instruction="Create an account and verify your email to continue.",
    )
    out = tmp_path / "out"
    out.mkdir()
    ok, msg = export.export_case(case, out, base_image="x", no_judge=True, judge_env={})
    assert not ok
    assert "SKIP" in msg


def test_needs_email_or_signup_negative() -> None:
    task = {
        "metadata": {"class": "collection"},
        "instruction": "Add an item to a list.",
    }
    skip, _ = export.needs_email_or_signup(task)
    assert skip is False


def test_main_exports_directory_and_writes_skipped_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    v2 = tmp_path / "v2"
    _write_case(v2, "v2-good", cls="collection")
    _write_case(v2, "v2-reg", cls="registration")
    out = tmp_path / "out"
    rc = export.main([str(v2), "-o", str(out), "--no-judge"])
    assert rc == 0
    assert (out / "v2-good" / "task.toml").is_file()
    assert not (out / "v2-reg").exists()
    skipped = (out / "SKIPPED.md").read_text()
    assert "v2-reg" in skipped


def test_sanitize_name() -> None:
    assert export._sanitize_name("v2-1100-Food_Cooking") == "v2-1100-food_cooking"
    assert export._sanitize_name("--weird..name--") == "weird..name"
