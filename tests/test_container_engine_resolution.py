"""Container-engine resolution is lazy: importing a module must not probe PATH."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture(autouse=True)
def _clear_engine_cache():
    """engine() memoizes; don't leak a faked result into the next test."""
    from clawbench.runner.run_support import config

    config.engine.cache_clear()
    yield
    config.engine.cache_clear()


# Every module that reaches the engine, plus the ones that only import
# something that does. batch is in the list because its job planning, --dry-run
# and --resume paths are useful on a host with no container runtime at all.
ENGINE_DEPENDENT_MODULES = (
    "clawbench.runner.run_support.config",
    "clawbench.runner.run_support.docker",
    "clawbench.runner.run_support.metadata",
    "clawbench.runner.run",
    "clawbench.runner.batch",
    "clawbench.eval.rescore",
)


def _import_in_subprocess(
    module: str, *, engine_on_path: bool
) -> subprocess.CompletedProcess:
    """Import ``module`` in a fresh interpreter, optionally hiding docker/podman."""

    code = textwrap.dedent(
        """
        import importlib
        import shutil
        import sys

        module, hide = sys.argv[1], sys.argv[2] == "hide"
        if hide:
            shutil.which = lambda _cmd: None
        importlib.import_module(module)
        print("imported")
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_ROOT)
    env.pop("CONTAINER_ENGINE", None)
    return subprocess.run(
        [sys.executable, "-c", code, module, "hide" if not engine_on_path else "show"],
        capture_output=True,
        env=env,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize("module", ENGINE_DEPENDENT_MODULES)
def test_import_succeeds_with_no_container_engine_on_path(module: str) -> None:
    """The regression this guards: ENGINE = _detect_engine() at module scope.

    That probe ended in a bare sys.exit(1), so importing any of these modules
    killed the interpreter on a host without docker or podman -- not an
    exception a caller could catch and degrade on.
    """
    result = _import_in_subprocess(module, engine_on_path=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "imported" in result.stdout


def test_engine_still_fails_fast_when_actually_needed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Laziness moves the failure, it does not remove it."""
    from clawbench.runner.run_support import config

    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda _cmd: None)
    config.engine.cache_clear()

    with pytest.raises(SystemExit) as excinfo:
        config.engine()

    assert excinfo.value.code == 1


@pytest.mark.parametrize("env_value", ["podman", "docker"])
def test_container_engine_env_var_wins(
    monkeypatch: pytest.MonkeyPatch, env_value: str
) -> None:
    from clawbench.runner.run_support import config

    monkeypatch.setenv("CONTAINER_ENGINE", env_value)
    monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
    config.engine.cache_clear()

    assert config.engine() == env_value


def test_container_engine_env_var_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    from clawbench.runner.run_support import config

    monkeypatch.setenv("CONTAINER_ENGINE", "containerd")
    config.engine.cache_clear()

    with pytest.raises(SystemExit) as excinfo:
        config.engine()

    assert excinfo.value.code == 1


def test_engine_probes_path_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every container command re-asks; shutil.which walks PATH each time."""
    from clawbench.runner.run_support import config

    calls: list[str] = []

    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd: calls.append(cmd) or cmd)
    config.engine.cache_clear()

    assert config.engine() == "docker"
    assert config.engine() == "docker"
    assert calls == ["docker"]


def test_engine_constant_still_resolves_but_warns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """config.ENGINE is kept for one release for out-of-tree callers."""
    config = importlib.import_module("clawbench.runner.run_support.config")

    monkeypatch.delenv("CONTAINER_ENGINE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
    config.engine.cache_clear()

    with pytest.deprecated_call():
        assert config.ENGINE == "docker"


def test_unknown_config_attribute_still_raises() -> None:
    config = importlib.import_module("clawbench.runner.run_support.config")

    with pytest.raises(AttributeError):
        config.NOT_A_REAL_SETTING
