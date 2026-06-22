from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

from clawbench.eval.harbor_adapter import (
    discover_cases,
    sanitize_task_name,
    unique_output_name,
    write_harbor_task,
)
from clawbench.runtime.harbor.verify import write_reward

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def _task(task_id: int = 47, extra_info: list[dict[str, str]] | None = None) -> dict:
    return {
        "metadata": {
            "task_id": task_id,
            "metaclass": "daily-life",
            "class": "personal-care",
            "description": "Book a moving helper",
            "sites_involved": ["example.com"],
            "platform": "example",
            "common_info": {
                "email_credentials": "credentials to use the assigned disposable email account",
                "user_info": "alex_green_personal_info.json; the dummy user's personal information",
                "user_resume": "PDF resume with disposable email account injected",
            },
        },
        "instruction": "Book a moving helper",
        "eval_schema": {"url_pattern": "example\\.com/checkout", "method": "POST"},
        "time_limit": 30,
        "extra_info": extra_info or [],
    }


def _write_case(root: Path, name: str, task: dict) -> Path:
    case = root / name
    case.mkdir(parents=True)
    (case / "task.json").write_text(json.dumps(task))
    return case


def test_discover_cases_ignores_empty_duplicate_dirs(tmp_path: Path) -> None:
    cases_dir = tmp_path / "v2"
    cases_dir.mkdir()
    _write_case(cases_dir, "v2-047-daily-life-personal-care-taskrabbit", _task())
    (cases_dir / "v2-047-daily-life-personal-care-taskrabbit 2").mkdir()

    cases = discover_cases(cases_dir)

    assert len(cases) == 1
    assert cases[0][0].name == "v2-047-daily-life-personal-care-taskrabbit"


def test_task_names_are_registry_safe_and_unique() -> None:
    seen: set[str] = set()
    assert sanitize_task_name("V2 Foo/Bar 2") == "v2-foo-bar-2"
    assert unique_output_name(Path("V2 Foo/Bar 2"), seen) == "bar-2"
    assert unique_output_name(Path("bar 2"), seen) == "bar-2-2"


def test_write_harbor_task_emits_expected_tree_and_extra_info(tmp_path: Path) -> None:
    task = _task(
        extra_info=[{"path": "extra_info/address_info.json", "description": "Address"}]
    )
    case = tmp_path / "case"
    (case / "extra_info").mkdir(parents=True)
    (case / "extra_info" / "address_info.json").write_text('{"address":"123 Main"}')

    out = write_harbor_task(
        task_dir=case,
        task=task,
        output_root=tmp_path / "out",
        output_name="v2-047-daily-life-personal-care-taskrabbit",
        org="clawbench",
        dataset_name="v2",
    )

    assert (out / "task.toml").is_file()
    assert (out / "environment" / "Dockerfile").is_file()
    assert not (out / "environment" / "harbor" / "Dockerfile").exists()
    assert (out / "environment" / "harbor" / "verify.py").is_file()
    assert (
        "+frag_keyframe+empty_moov+default_base_moof"
        in (out / "environment" / "runtime-server" / "server.py").read_text()
    )
    assert (out / "steps" / "run" / "instruction.md").is_file()
    assert (out / "steps" / "run" / "workdir" / "setup.sh").is_file()
    assert (out / "steps" / "run" / "workdir" / "eval-schema.json").is_file()
    assert (out / "steps" / "run" / "workdir" / "task.json").is_file()
    assert (
        out / "steps" / "run" / "workdir" / "extra_info" / "address_info.json"
    ).is_file()
    assert (out / "steps" / "run" / "tests" / "test.sh").is_file()
    assert (out / "steps" / "run" / "tests" / "task.json").is_file()
    assert (out / "steps" / "run" / "solution" / "solve.sh").is_file()

    config = tomllib.loads((out / "task.toml").read_text())
    assert config["schema_version"] == "1.3"
    assert (
        config["task"]["name"] == "clawbench/v2-047-daily-life-personal-care-taskrabbit"
    )
    assert config["environment"]["workdir"] == "/app"
    assert config["environment"]["network_mode"] == "public"
    assert config["environment"]["env"]["BROWSER_CDP_URL"] == "http://127.0.0.1:9223"
    assert config["environment"]["env"]["PLAYWRIGHT_CDP_URL"] == "http://127.0.0.1:9223"
    assert config["steps"][0]["agent"]["timeout_sec"] == 1800.0
    assert (
        "http://127.0.0.1:9223"
        in (out / "steps" / "run" / "instruction.md").read_text()
    )
    assert "BROWSER_CDP_URL" in (out / "steps" / "run" / "instruction.md").read_text()


def test_harbor_adapter_cli_smoke(tmp_path: Path) -> None:
    out = tmp_path / "harbor-v2"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "clawbench.eval.harbor_adapter",
            "--output-dir",
            str(out),
            "--limit",
            "1",
            "--overwrite",
        ],
        capture_output=True,
        env=env,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    task_tomls = list(out.glob("*/task.toml"))
    assert len(task_tomls) == 1
    tomllib.loads(task_tomls[0].read_text())


def test_harbor_adapter_help_without_container_runtime(tmp_path: Path) -> None:
    code = textwrap.dedent(
        """
        import runpy
        import shutil
        import sys

        shutil.which = lambda _cmd: None
        sys.argv = ["clawbench.eval.harbor_adapter", "--help"]
        runpy.run_module("clawbench.eval.harbor_adapter", run_name="__main__")
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "usage" in (result.stdout + result.stderr).lower()


def test_harbor_verifier_reward_json_contains_metadata(tmp_path: Path) -> None:
    write_reward(
        0.0,
        {
            "intercepted": True,
            "judge_match": False,
            "reason": "wrong payload",
            "task_id": 47,
        },
        output_dir=tmp_path,
    )

    assert (tmp_path / "reward.txt").read_text() == "0.0"
    reward = json.loads((tmp_path / "reward.json").read_text())
    detailed = json.loads((tmp_path / "clawbench-result.json").read_text())
    assert reward == detailed
    assert reward == {
        "reward": 0.0,
        "intercepted": True,
        "judge_match": False,
        "reason": "wrong payload",
        "task_id": 47,
    }
