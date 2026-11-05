"""Tests for the runtime harness agent exit status handoff."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER = (
    ROOT / "src" / "clawbench" / "runtime" / "harnesses" / "base" / "agent-status.sh"
)
BASH = shutil.which("bash")


def _bash_path(path: Path) -> str:
    """Translate a Windows path for the MSYS bash used by the local tests."""
    drive = path.drive.rstrip(":").lower()
    return f"/{drive}{path.as_posix()[2:]}"


@pytest.mark.skipif(
    BASH is None, reason="bash is required to exercise the harness helper"
)
@pytest.mark.parametrize(
    ("body", "expected_code", "expected_reason"),
    [
        ('(exit 0) & pid=$!; capture_agent_exit "$pid"', 0, "self_exit"),
        ('(exit 17) & pid=$!; capture_agent_exit "$pid"', 17, "self_exit"),
        ("capture_agent_command bash -c 'exit 0'", 0, "self_exit"),
        ("capture_agent_command bash -c 'exit 17'", 17, "self_exit"),
        ("capture_watchdog_stop", None, "watchdog"),
    ],
)
def test_agent_status_helper_records_clean_crash_and_watchdog(
    tmp_path: Path, body: str, expected_code: int | None, expected_reason: str
) -> None:
    if BASH is None:
        pytest.skip("bash is required to exercise the harness helper")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    env = os.environ.copy()
    env["AGENT_STATUS_DIR"] = str(data_dir)
    command = f"source '{_bash_path(HELPER)}'\n{body}\n"

    result = subprocess.run(
        [BASH, "-c", command], env=env, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    status = json.loads((data_dir / "agent-status.json").read_text(encoding="utf-8"))
    assert status == {
        "agent_exit_code": expected_code,
        "agent_exit_reason": expected_reason,
    }


def test_all_harness_scripts_use_the_exit_status_handoff() -> None:
    harness_root = ROOT / "src" / "clawbench" / "runtime" / "harnesses"
    run_scripts = sorted(harness_root.glob("*/run-*.sh"))

    assert run_scripts
    for script in run_scripts:
        source = script.read_text(encoding="utf-8")
        assert "source /agent-status.sh" in source, script
        if "AGENT_PID=" in source:
            assert "capture_agent_exit" in source, script
            assert "capture_watchdog_stop" in source, script
        elif script.parent.name == "random-click":
            assert "capture_agent_command python3 /random_clicker.py" in source, script
            assert 'echo "agent_failed" > /data/.stop-reason' in source, script
        else:
            assert "write_agent_status 0 self_exit" in source, script
