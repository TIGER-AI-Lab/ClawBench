"""Atomic metadata writes and batch reporting that survives a bad run-meta.json."""

from __future__ import annotations

import importlib
import json
import shutil
from pathlib import Path

import pytest

from clawbench.runner.batch import print_run_stats
from clawbench.utils.jsonio import read_json_or_none, write_json_atomic


def _make_run(model_dir: Path, name: str, meta: str | None) -> Path:
    """Create a run directory shaped like a real one, with raw `meta` text."""
    run_dir = model_dir / name
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "data" / "actions.jsonl").write_text('{"type": "click"}\n')
    if meta is not None:
        (run_dir / "run-meta.json").write_text(meta, encoding="utf-8")
    return run_dir


# --- write_json_atomic -------------------------------------------------------


def test_write_json_atomic_roundtrips_and_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "run-meta.json"

    write_json_atomic(target, {"test_case": "001-foo", "intercepted": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {
        "test_case": "001-foo",
        "intercepted": True,
    }


def test_write_json_atomic_leaves_no_temp_files(tmp_path: Path) -> None:
    write_json_atomic(tmp_path / "run-meta.json", {"a": 1})

    assert [p.name for p in tmp_path.iterdir()] == ["run-meta.json"]


def test_write_json_atomic_keeps_previous_file_when_serialization_fails(
    tmp_path: Path,
) -> None:
    """A failed write must not truncate the file that was already there."""
    target = tmp_path / "run-meta.json"
    write_json_atomic(target, {"generation": 1})

    with pytest.raises(TypeError):
        write_json_atomic(target, {"bad": object()})

    assert json.loads(target.read_text(encoding="utf-8")) == {"generation": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["run-meta.json"]


def test_write_run_meta_is_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # metadata resolves a container engine at import time; see conftest note.
    monkeypatch.setattr(shutil, "which", lambda cmd: cmd)
    metadata = importlib.import_module("clawbench.runner.run_support.metadata")

    metadata.write_run_meta(tmp_path / "out", {"test_case": "001-foo"})

    written = tmp_path / "out" / "run-meta.json"
    assert json.loads(written.read_text(encoding="utf-8")) == {"test_case": "001-foo"}
    assert [p.name for p in (tmp_path / "out").iterdir()] == ["run-meta.json"]


# --- read_json_or_none -------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ['{"test_case": "001-foo"', "", "not json at all", "\udcff"],
    ids=["truncated", "empty", "garbage", "undecodable"],
)
def test_read_json_or_none_returns_none_for_unreadable(
    tmp_path: Path, raw: str
) -> None:
    target = tmp_path / "run-meta.json"
    target.write_bytes(raw.encode("utf-8", "surrogateescape"))

    assert read_json_or_none(target) is None


def test_read_json_or_none_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert read_json_or_none(tmp_path / "nope.json") is None


# --- print_run_stats regression (issue #303) ---------------------------------


def test_print_run_stats_survives_truncated_run_meta(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One truncated run-meta.json must not abort stats for the whole batch."""
    model_dir = tmp_path / "some-model"
    model_dir.mkdir()
    _make_run(model_dir, "run-good", json.dumps({"test_case": "001-good"}))
    _make_run(model_dir, "run-truncated", '{"test_case": "002-trunc"')

    print_run_stats(tmp_path)

    out = capsys.readouterr().out
    assert "001-good" in out
    assert "run-truncated" in out
    assert "WARNING: unreadable" in out


def test_print_run_stats_survives_non_object_run_meta(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Valid JSON that is not an object must not blow up on .get() either."""
    model_dir = tmp_path / "some-model"
    model_dir.mkdir()
    _make_run(model_dir, "run-listy", "[1, 2, 3]")

    print_run_stats(tmp_path)

    out = capsys.readouterr().out
    assert "run-listy" in out
    assert "WARNING: unreadable" in out
