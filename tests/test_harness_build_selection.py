"""Build dependency selection must cover shared code, not just Dockerfile edits."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/ci/select_harness_builds.py"
spec = importlib.util.spec_from_file_location("select_harness_builds", SCRIPT)
assert spec and spec.loader
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)
ROOT = Path("src/clawbench/runtime")


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    for name in ("base", "hermes", "codex"):
        dockerfile = ROOT / "harnesses" / name / f"Dockerfile.{name}"
        dockerfile.parent.mkdir(parents=True)
        dockerfile.write_text("FROM scratch\n")
    return ROOT


@pytest.mark.parametrize(
    "changed",
    [
        "runtime-server/server.py",
        "runtime-server/pyproject.toml",
        "runtime-server/uv.lock",
        "runtime-server/deleted-module.py",
        "harnesses/base/entrypoint.sh",
        "chrome-extension/manifest.json",
        "shared/alex_green_personal_info.json",
        "harnesses/harnesses.yaml",
        "harnesses/harness.schema.json",
    ],
)
def test_shared_dependencies_select_every_native_harness(
    runtime: Path, changed: str
) -> None:
    selected = selector.select_dockerfiles(runtime, [(runtime / changed).as_posix()])
    assert [p.parent.name for p in selected] == ["codex", "hermes"]


def test_harness_changes_are_deduplicated_and_exclude_removed_images(
    runtime: Path,
) -> None:
    changes = [
        "harnesses/hermes/run-hermes.sh",
        "harnesses/hermes/removed-setup.sh",
        "harnesses/deleted-harness/Dockerfile.deleted-harness",
    ]
    selected = selector.select_dockerfiles(
        runtime, [(runtime / p).as_posix() for p in changes]
    )
    assert selected == [runtime / "harnesses/hermes/Dockerfile.hermes"]


@pytest.mark.parametrize(
    "changes",
    [
        None,
        [],
        [".github/workflows/check-harness-build.yml"],
        ["scripts/ci/select_harness_builds.py"],
    ],
)
def test_manual_or_selector_changes_exercise_full_matrix(
    runtime: Path, changes: list[str] | None
) -> None:
    assert len(selector.select_dockerfiles(runtime, changes)) == 2


def test_harbor_only_change_does_not_select_native_harnesses(runtime: Path) -> None:
    assert (
        selector.select_dockerfiles(
            runtime, [(runtime / "harbor/verify.py").as_posix()]
        )
        == []
    )


def test_cli_emits_actions_matrix_count_and_readable_summary(
    runtime: Path, tmp_path: Path
) -> None:
    changed = tmp_path / "changed"
    changed.write_bytes(
        (str(runtime / "runtime-server/module with spaces.py") + "\0").encode()
    )
    output = tmp_path / "github-output"
    summary = tmp_path / "github-summary"
    output.write_text("existing=value\n")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--changed-files",
            str(changed),
            "--github-output",
            str(output),
            "--github-summary",
            str(summary),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert values["existing"] == "value"
    assert values["count"] == "2"
    matrix = json.loads(values["matrix"])
    assert matrix == json.loads(result.stdout)
    assert matrix["include"] == [
        {
            "harness": name,
            "dockerfile": f"{runtime}/harnesses/{name}/Dockerfile.{name}",
            "image": f"clawbench-{name}",
        }
        for name in ("codex", "hermes")
    ]
    assert "clawbench-codex" in summary.read_text()
    assert "clawbench-hermes" in summary.read_text()


def test_empty_matrix_has_numeric_zero_count(runtime: Path, tmp_path: Path) -> None:
    changed = tmp_path / "changed"
    changed.write_bytes((str(runtime / "harbor/verify.py") + "\0").encode())
    output = tmp_path / "github-output"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--changed-files",
            str(changed),
            "--github-output",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    assert output.read_text() == 'matrix={"include":[]}\ncount=0\n'
