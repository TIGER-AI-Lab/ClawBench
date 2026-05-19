"""Host-side CLI diagnostics that avoid container/runtime dependencies."""

from __future__ import annotations

import subprocess
import sys
import textwrap
import os
from pathlib import Path

import pytest


SRC_ROOT = Path(__file__).resolve().parents[1] / "src"

HELP_MODULES = (
    "clawbench.tui",
    "clawbench.runner.run",
    "clawbench.runner.batch",
)


@pytest.mark.parametrize("module", HELP_MODULES)
def test_module_help_does_not_require_container_runtime(module: str) -> None:
    """Help output should work even when docker/podman are unavailable.

    The subprocess monkeypatches ``shutil.which`` before running the module so
    import-time container-engine probes see a host with no container runtime.
    This keeps the test fully Python-based and cross-platform.
    """

    code = textwrap.dedent(
        """
        import runpy
        import shutil
        import sys

        module = sys.argv[1]
        shutil.which = lambda _cmd: None
        sys.argv = [module, "--help"]
        runpy.run_module(module, run_name="__main__")
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)

    result = subprocess.run(
        [sys.executable, "-c", code, module],
        capture_output=True,
        env=env,
        text=True,
        timeout=30,
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "usage" in combined_output.lower()
