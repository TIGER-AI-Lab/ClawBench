"""Regression test for a missing/invalid --judge model (issue #302).

Before the fix, load_model_config() called sys.exit() on a bad model name.
When that happened for the *judge* model — after the agent had already run
and produced results — the resulting SystemExit escaped both the judge
stage's `except Exception` and run()'s top-level `except Exception`, since
SystemExit is a BaseException, not an Exception. The process died without
ever calling write_run_meta(), silently discarding the run's results.

The fix has two halves, one test each:

  * A bad --judge is now rejected at startup, before the agent runs at all,
    so a command-line typo costs seconds instead of half an hour.
  * A judge failure that only surfaces mid-run is caught and degraded to a
    judge_setup_failed outcome, and the run still reaches write_run_meta().

These drive run_mod.main() through a fully mocked agent run, skipping the
docker/network/email side effects.
"""

from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from clawbench.runner.run_support.results import JUDGE_INCONCLUSIVE_EXIT


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


def _prepare_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    judge_model: str,
) -> tuple[ModuleType, list[tuple[Path, dict[str, Any]]], list[str]]:
    """Mock out every side effect of a run; return the module, the
    run-meta writes it performed, and a log of docker calls."""
    run_mod = _import_run_module(monkeypatch)

    task_dir = tmp_path / "case"
    task_dir.mkdir()
    (task_dir / "task.json").write_text(
        json.dumps(
            {
                "instruction": "Do the task",
                "eval_schema": {"url_pattern": "example", "method": "POST"},
                "time_limit": 1,
            }
        )
    )
    personal_info_dir = tmp_path / "personal-info"
    personal_info_dir.mkdir()

    monkeypatch.setattr(
        run_mod.sys,
        "argv",
        [
            "clawbench-run",
            str(task_dir),
            "model-a",
            "--judge",
            judge_model,
            "--output-dir",
            str(tmp_path / "out"),
            "--no-build",
            "--no-upload",
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

    class FakeProvider:
        name = "local"

        def start(self, task: dict, time_limit_s: int):
            from clawbench.runner.run_support.browser_runtime.providers import (
                BrowserSession,
            )

            return BrowserSession(
                provider="local",
                cdp_url="http://127.0.0.1:9222",
                mode="local",
                recording_mode="x11",
                local_viewer_port=6080,
            )

        def finalize(self, session, output_dir):
            pass

        def cleanup(self, session):
            pass

    monkeypatch.setattr(
        run_mod, "make_browser_runtime_provider", lambda args, env: FakeProvider()
    )
    monkeypatch.setattr(run_mod, "preflight_model_api", lambda model_cfg: None)

    def fake_load_model_config(model: str) -> dict:
        if model == "missing-judge-model":
            raise run_mod.ModelConfigError(
                f"model '{model}' not found in models.yaml. Available models: model-a"
            )
        return {
            "model": model,
            "base_url": "https://api.example.test/v1",
            "api_type": "openai-completions",
            "api_key": "secret-key",
            "api_keys": ["secret-key"],
        }

    monkeypatch.setattr(run_mod, "load_model_config", fake_load_model_config)
    monkeypatch.setattr(
        run_mod,
        "create_email",
        lambda pm_key, pm_domain: ("agent@example.test", "email-pw"),
    )
    monkeypatch.setattr(run_mod, "delete_email", lambda pm_key, email: None)
    monkeypatch.setattr(
        run_mod,
        "prepare_personal_info",
        lambda shared_root, email, email_pw, output_dir: (personal_info_dir, {}),
    )
    monkeypatch.setattr(run_mod, "copy_extra_info", lambda task, task_dir, dest: [])
    monkeypatch.setattr(run_mod, "build_instruction", lambda task: "Do the task")
    docker_calls: list[str] = []
    monkeypatch.setattr(
        run_mod, "docker_run", lambda *args, **kwargs: docker_calls.append("run")
    )
    monkeypatch.setattr(run_mod, "docker_wait", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_mod, "docker_logs", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_mod, "docker_copy", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_mod, "docker_rm", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_mod, "_fix_data_ownership", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_mod, "ensure_interception", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        run_mod, "print_results", lambda *args, **kwargs: True
    )  # stage 1 (intercepted) passed
    monkeypatch.setattr(
        run_mod, "remove_transient_usage_artifact", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        run_mod,
        "classify_run",
        lambda *args, **kwargs: {
            "result_category": "pass",
            "failure_category": None,
            "infra_failure": False,
            "adjusted_eligible": True,
            "infra_flags": [],
            "metrics": {},
        },
    )

    written: list[tuple[Path, dict[str, Any]]] = []
    monkeypatch.setattr(
        run_mod,
        "make_run_meta",
        lambda **kwargs: {"failure_reason": kwargs.get("failure_reason")},
    )
    monkeypatch.setattr(
        run_mod,
        "write_run_meta",
        lambda output_dir, meta: written.append((output_dir, meta)),
    )

    return run_mod, written, docker_calls


def test_bad_judge_model_is_rejected_before_the_agent_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Ask 1 of the issue: catch a --judge typo at startup, not 30 minutes in."""
    run_mod, written, docker_calls = _prepare_run(
        monkeypatch, tmp_path, "missing-judge-model"
    )

    with pytest.raises(SystemExit) as excinfo:
        run_mod.main()

    assert excinfo.value.code == 1
    assert docker_calls == []  # the agent never ran
    assert written == []  # and there is no run to record
    out = capsys.readouterr().out
    assert "--judge" in out
    assert "missing-judge-model" in out


def test_judge_failure_after_the_run_still_writes_run_meta(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Ask 2, and the invariant: a completed agent run always writes metadata.

    Before the fix, a ModelConfigError surfacing here was a SystemExit, which
    escaped both the judge stage's `except Exception` and run()'s top-level
    handler, killing the process before write_run_meta().
    """
    run_mod, written, docker_calls = _prepare_run(monkeypatch, tmp_path, "model-a")

    import clawbench.runner.judge as judge_mod

    def explode(*args: Any, **kwargs: Any) -> dict:
        raise run_mod.ModelConfigError("judge backend went away mid-run")

    monkeypatch.setattr(judge_mod, "judge_request", explode)

    with pytest.raises(SystemExit) as excinfo:
        run_mod.main()

    # A clean exit, not an uncaught crash. #299 gave the inconclusive verdict
    # its own code so a judge outage is not counted as the model failing; this
    # run intercepted, and only stage 2 is missing.
    assert excinfo.value.code == JUDGE_INCONCLUSIVE_EXIT
    assert docker_calls == ["run"]  # the agent did run

    # The core regression: its results must not be silently discarded.
    assert len(written) == 1
    meta = written[0][1]
    assert meta["judge_match"] is None
    assert "judge_setup_failed" in meta["judge"]["reason"]
    assert "went away mid-run" in meta["judge"]["reason"]
    assert meta["pass"] is False


def test_model_config_error_is_catchable_as_a_plain_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point: SystemExit is a BaseException and slips past
    `except Exception`. ModelConfigError must not."""
    ModelConfigError = _import_run_module(monkeypatch).ModelConfigError

    assert issubclass(ModelConfigError, Exception)
    assert not issubclass(ModelConfigError, SystemExit)

    try:
        raise ModelConfigError("boom")
    except Exception as e:
        assert "boom" in str(e)
    else:  # pragma: no cover
        pytest.fail("ModelConfigError was not caught by `except Exception`")


def test_missing_models_yaml_is_also_catchable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """load_model_config() calls load_models_yaml(). If that still exited,
    a SystemExit would escape the judge stage exactly as before."""
    config = _import_run_module(monkeypatch)
    cfg_mod = sys.modules["clawbench.runner.run_support.config"]
    monkeypatch.setattr(cfg_mod, "MODELS_YAML", tmp_path / "absent.yaml")

    with pytest.raises(config.ModelConfigError) as excinfo:
        cfg_mod.load_models_yaml()

    assert "absent.yaml" in str(excinfo.value)

    # And the same call reached through load_model_config stays catchable.
    try:
        cfg_mod.load_model_config("anything")
    except Exception as e:
        assert isinstance(e, config.ModelConfigError)
    else:  # pragma: no cover
        pytest.fail("expected ModelConfigError")
