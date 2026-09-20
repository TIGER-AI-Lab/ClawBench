"""Task-source adapter registry, shared schema, and `clawbench-sources` CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from clawbench.adapters import (
    AdapterError,
    ClawBenchTask,
    ExtraInfo,
    ScoringLayer,
    get_adapter,
    offline,
    parse_source_spec,
    registered_sources,
    source_cache_dir,
)
from clawbench.adapters import cli as sources_cli
from clawbench.adapters.schema import AdapterWarning
from clawbench.utils.paths import ASSET_ROOT

TASK_SCHEMA = ASSET_ROOT / "test-cases" / "task.schema.json"


def _write_task(directory: Path, name: str, **overrides: object) -> Path:
    task = {
        "instruction": "Book a table for two.",
        "eval_schema": {"url_pattern": "/api/book", "method": "POST"},
        "time_limit": 10,
    }
    task.update(overrides)
    task_dir = directory / name
    task_dir.mkdir(parents=True)
    task_file = task_dir / "task.json"
    task_file.write_text(json.dumps(task), encoding="utf-8")
    return task_file


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_native_source_is_registered() -> None:
    assert "clawbench-native" in registered_sources()
    assert registered_sources() == tuple(sorted(registered_sources()))

    adapter = get_adapter("clawbench-native")
    assert adapter.bundled
    assert adapter.upstream is None
    assert ScoringLayer.SUBMISSION_INTERCEPT in adapter.scoring_layers


def test_unknown_source_names_the_registered_ones() -> None:
    with pytest.raises(AdapterError) as exc_info:
        get_adapter("not-a-benchmark")

    assert "not-a-benchmark" in str(exc_info.value)
    assert "clawbench-native" in str(exc_info.value)


@pytest.mark.parametrize(
    ("spec", "expected_name", "expected_path"),
    [
        ("claw-eval", "claw-eval", None),
        ("claw-eval:/srv/claw-eval", "claw-eval", Path("/srv/claw-eval")),
        # A bare Windows path is not a name:path spec.
        ("C:/repos/claw-eval", "C:/repos/claw-eval", None),
    ],
)
def test_parse_source_spec(
    spec: str, expected_name: str, expected_path: Path | None
) -> None:
    assert parse_source_spec(spec) == (expected_name, expected_path)


def test_source_cache_dir_prefers_explicit_then_xdg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("CLAWBENCH_SOURCES_DIR", raising=False)
    assert source_cache_dir() == tmp_path / "xdg" / "clawbench" / "sources"

    monkeypatch.setenv("CLAWBENCH_SOURCES_DIR", str(tmp_path / "explicit"))
    assert source_cache_dir() == tmp_path / "explicit"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", False), ("0", False), ("false", False), ("no", False), ("1", True)],
)
def test_offline_flag(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: bool
) -> None:
    monkeypatch.setenv("CLAWBENCH_OFFLINE", value)
    assert offline() is expected


# ---------------------------------------------------------------------------
# Shared schema
# ---------------------------------------------------------------------------


def test_task_rejects_missing_and_impossible_fields() -> None:
    base: dict[str, object] = {
        "task_id": "t1",
        "source": "demo",
        "instruction": "do the thing",
        "time_limit": 10,
    }

    with pytest.raises(ValueError, match="instruction"):
        ClawBenchTask(**{**base, "instruction": "   "})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="time_limit must be greater than 0"):
        ClawBenchTask(**{**base, "time_limit": 0})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="time_limit must be a number"):
        ClawBenchTask(**{**base, "time_limit": "10"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="eval_schema.method"):
        ClawBenchTask(**{**base, "eval_schema": {"url_pattern": "/x"}})  # type: ignore[arg-type]


def test_submission_intercept_requires_an_eval_schema() -> None:
    with pytest.raises(ValueError, match="submission_intercept"):
        ClawBenchTask(
            task_id="t1",
            source="demo",
            instruction="do the thing",
            time_limit=10,
            scoring_layers=(ScoringLayer.SUBMISSION_INTERCEPT,),
        )


def test_unsupported_layer_is_reported_rather_than_scored() -> None:
    task = ClawBenchTask(
        task_id="t1",
        source="demo",
        instruction="do the thing",
        time_limit=10,
        scoring_layers=(ScoringLayer.LLM_JUDGE_ONLY,),
    )

    assert task.supports(ScoringLayer.LLM_JUDGE_ONLY)
    assert not task.supports(ScoringLayer.SUBMISSION_INTERCEPT)
    # No interception contract means no native task.json can be rendered.
    with pytest.raises(ValueError, match="eval_schema"):
        task.to_task_json()


def test_to_task_json_matches_the_published_task_schema() -> None:
    task = ClawBenchTask(
        task_id="demo-001",
        source="demo-bench",
        source_id="upstream-42",
        instruction="Book a table for two.",
        time_limit=12.5,
        eval_schema={"url_pattern": "/api/book", "method": "POST"},
        category="dining",
        scoring_layers=(ScoringLayer.SUBMISSION_INTERCEPT,),
        extra_info=(ExtraInfo(description="Seating chart", path="chart.pdf"),),
        judge_context={"rubric": "Table booked for two."},
        metadata={
            "description": "Reserve a table",
            "sites_involved": ["opentable.com"],
        },
    )

    rendered = task.to_task_json()

    assert rendered["metadata"]["source"] == "demo-bench"
    assert rendered["metadata"]["source_id"] == "upstream-42"
    assert rendered["time_limit"] == 12.5
    assert rendered["extra_info"] == [
        {"path": "chart.pdf", "description": "Seating chart"}
    ]

    schema = json.loads(TASK_SCHEMA.read_text(encoding="utf-8"))
    # `metadata` carries provenance keys the corpus schema does not require, so
    # validate against the required half of the contract the runner reads.
    validator = Draft202012Validator(
        {
            "type": "object",
            "required": schema["required"],
            "properties": {
                key: schema["properties"][key]
                for key in ("instruction", "eval_schema", "time_limit", "extra_info")
            },
        }
    )
    assert list(validator.iter_errors(rendered)) == []


def test_adapter_warning_renders_source_task_and_upstream() -> None:
    warning = AdapterWarning(
        source="mind2web",
        task_id="t1",
        field_name="time_limit",
        message="upstream has no per-task limit",
        fallback="300s",
        upstream_sha="abc1234",
    )

    text = str(warning)
    assert "[mind2web/t1]" in text
    assert "time_limit" in text
    assert "using 300s" in text
    assert "abc1234" in text


# ---------------------------------------------------------------------------
# Native adapter
# ---------------------------------------------------------------------------


def test_native_adapter_reads_a_suite_directory(tmp_path: Path) -> None:
    _write_task(
        tmp_path,
        "001-dining-reservation",
        metadata={"task_id": 1, "class": "dining"},
        extra_info=[{"path": "chart.pdf", "description": "Seating chart"}],
        judge_context={"rubric": "Table booked."},
    )
    _write_task(tmp_path, "002-shopping-cart")

    tasks = get_adapter("clawbench-native").load(tmp_path)

    assert [task.task_id for task in tasks] == [
        "001-dining-reservation",
        "002-shopping-cart",
    ]
    first = tasks[0]
    assert first.source == "clawbench-native"
    assert first.source_id == "1"
    assert first.category == "dining"
    assert first.time_limit == 10
    assert first.extra_info == (
        ExtraInfo(description="Seating chart", path="chart.pdf"),
    )
    assert first.judge_context == {"rubric": "Table booked."}
    # The identity mapping loses nothing, so it never warns.
    assert first.warnings == ()


def test_native_adapter_falls_back_to_a_corpus_root(tmp_path: Path) -> None:
    _write_task(tmp_path / "v1", "001-a")
    _write_task(tmp_path / "v2", "v2-001-b")

    tasks = get_adapter("clawbench-native").load(tmp_path)

    assert [task.task_id for task in tasks] == ["001-a", "v2-001-b"]


def test_native_adapter_reports_unreadable_sources(tmp_path: Path) -> None:
    adapter = get_adapter("clawbench-native")

    with pytest.raises(AdapterError, match="not a directory"):
        adapter.load(tmp_path / "missing")
    with pytest.raises(AdapterError, match="no <task>/task.json"):
        adapter.load(tmp_path)

    broken = tmp_path / "003-broken"
    broken.mkdir()
    (broken / "task.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(AdapterError, match="cannot read"):
        adapter.load(tmp_path)


def test_native_adapter_surfaces_invalid_tasks_with_their_path(tmp_path: Path) -> None:
    _write_task(tmp_path, "004-no-instruction", instruction="")

    with pytest.raises(AdapterError, match="instruction"):
        get_adapter("clawbench-native").load(tmp_path)


def test_native_adapter_loads_the_bundled_v2_suite() -> None:
    tasks = get_adapter("clawbench-native").load(ASSET_ROOT / "test-cases" / "v2")

    assert len(tasks) > 100
    for task in tasks:
        assert task.eval_schema is not None
        assert task.supports(ScoringLayer.SUBMISSION_INTERCEPT)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_sources_cli_lists_registered_sources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert sources_cli.main([]) == 0

    out = capsys.readouterr().out
    assert "SOURCE" in out
    assert "clawbench-native" in out
    assert "bundled" in out


def test_sources_cli_list_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert sources_cli.main(["list", "--json"]) == 0

    rows = json.loads(capsys.readouterr().out)
    native = next(row for row in rows if row["name"] == "clawbench-native")
    assert native["state"] == "bundled"
    assert native["upstream"] is None
    assert "submission_intercept" in native["scoring_layers"]


def test_sources_cli_show_includes_the_field_mapping(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert sources_cli.main(["show", "clawbench-native"]) == 0

    out = capsys.readouterr().out
    assert "scoring layers:" in out
    assert "Field mapping" in out


def test_sources_cli_cases_lists_tasks(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _write_task(tmp_path, "001-dining-reservation")

    assert (
        sources_cli.main(
            ["cases", "clawbench-native", "--path", str(tmp_path), "--json"]
        )
        == 0
    )

    rows = json.loads(capsys.readouterr().out)
    assert [row["task_id"] for row in rows] == ["001-dining-reservation"]
    assert rows[0]["warnings"] == []


def test_sources_cli_reports_unknown_sources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert sources_cli.main(["show", "not-a-benchmark"]) == 1

    assert "not-a-benchmark" in capsys.readouterr().err
