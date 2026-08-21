"""rescore CLI portability: workspace-resolved defaults and loud failures."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest
import yaml

from clawbench.eval import rescore
from clawbench.utils.model_config import MODELS_YAML, load_model_config
from clawbench.utils.paths import WORKSPACE_ROOT


@pytest.fixture
def stub_judge(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reach the scan-root check without needing real model credentials."""
    monkeypatch.setattr(
        rescore,
        "load_model_config",
        lambda model, models_yaml=None: {
            "model": model,
            "base_url": "https://example.test",
            "api_type": "openai-completions",
            "api_key": "k",
            "api_keys": ["k"],
        },
    )


# --- portable defaults (asks 1 and 2) ----------------------------------------


def test_defaults_are_workspace_relative() -> None:
    args = rescore.build_parser().parse_args([])

    assert args.sweep_root == WORKSPACE_ROOT / "test-output"
    assert args.models_yaml == MODELS_YAML


def test_defaults_do_not_ship_a_maintainers_home_layout() -> None:
    """Regression guard against re-introducing ~/work/ClawBench/... defaults.

    Asserted against the source rather than the resolved paths: a checkout can
    legitimately sit anywhere, including under a directory literally named
    ``work/ClawBench`` (GitHub Actions checks this repo out to
    ``/home/runner/work/ClawBench/ClawBench``), so only the absence of a
    home-anchored default is meaningful.
    """
    src = inspect.getsource(rescore.build_parser)

    assert "Path.home()" not in src
    assert "expanduser" not in src


# --- loud failure instead of a silent no-op (ask 3) --------------------------


def test_missing_sweep_root_errors_instead_of_exiting_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stub_judge: None,
) -> None:
    missing = tmp_path / "nope"
    monkeypatch.setattr(
        sys, "argv", ["clawbench-rescore", "--sweep-root", str(missing)]
    )

    rc = rescore.main()

    assert rc == 2
    err = capsys.readouterr().err
    assert "is not a directory" in err
    assert str(missing) in err


def test_empty_sweep_root_errors_instead_of_exiting_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stub_judge: None,
) -> None:
    """A real directory holding no runs is still a mis-pointed CLI."""
    empty = tmp_path / "test-output"
    empty.mkdir()
    monkeypatch.setattr(sys, "argv", ["clawbench-rescore", "--sweep-root", str(empty)])

    rc = rescore.main()

    assert rc == 2
    assert "no runs found" in capsys.readouterr().err


def test_missing_only_batch_names_that_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    stub_judge: None,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["clawbench-rescore", "--only-batch", str(tmp_path / "batch-gone")],
    )

    rc = rescore.main()

    assert rc == 2
    assert "--only-batch" in capsys.readouterr().err


# --- shared model loader (ask 4) ---------------------------------------------


def _write_models(tmp_path: Path, entry: dict) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(yaml.safe_dump({"judge-model": entry}), encoding="utf-8")
    return path


def test_load_model_config_accepts_the_api_keys_list_form(tmp_path: Path) -> None:
    """rescore re-parsed the YAML itself and rejected the api_keys list form
    that every other entry point accepts."""
    path = _write_models(
        tmp_path,
        {
            "base_url": "https://example.test",
            "api_type": "openai-completions",
            "api_keys": ["first", "second"],
        },
    )

    cfg = load_model_config("judge-model", path)

    assert cfg["api_key"] == "first"
    assert cfg["api_keys"] == ["first", "second"]


def test_load_model_config_still_accepts_the_api_key_scalar_form(
    tmp_path: Path,
) -> None:
    path = _write_models(
        tmp_path,
        {
            "base_url": "https://example.test",
            "api_type": "openai-completions",
            "api_key": "only",
        },
    )

    cfg = load_model_config("judge-model", path)

    assert cfg["api_key"] == "only"
    assert cfg["api_keys"] == ["only"]


def test_load_model_config_reports_the_explicit_path_on_a_bad_model(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_models(
        tmp_path,
        {
            "base_url": "https://example.test",
            "api_type": "openai-completions",
            "api_key": "k",
        },
    )

    with pytest.raises(SystemExit):
        load_model_config("not-there", path)

    assert str(path) in capsys.readouterr().out


def test_load_models_yaml_falls_back_to_the_workspace_default() -> None:
    """Passing no path must keep resolving to MODELS_YAML for the runner."""
    from clawbench.utils import model_config

    sig = inspect.signature(model_config.load_models_yaml)
    assert sig.parameters["models_yaml"].default is None


# --- the tool must not require a container engine ----------------------------


def test_rescore_does_not_depend_on_the_container_probing_config_module() -> None:
    """rescore only scores finished runs. run_support.config probes for a
    container engine at import time and exits when none is installed, so
    pulling it in would make the tool unusable on a host without Docker."""
    src = Path(rescore.__file__).read_text(encoding="utf-8")

    assert "run_support.config" not in src
    assert "run_support import config" not in src
