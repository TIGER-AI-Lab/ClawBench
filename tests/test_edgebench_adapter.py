"""Tests for the EdgeBench/SForge benchmark exporter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from clawbench.eval import edgebench_adapter as ea
from clawbench.eval.harbor_adapter import DEFAULT_CASES_DIR, discover_cases


@pytest.fixture(scope="module")
def one_case():
    cases = discover_cases(DEFAULT_CASES_DIR)
    if not cases:
        pytest.skip("no bundled V2 cases")
    return cases[0]


def test_benchmark_yaml_valid() -> None:
    doc = yaml.safe_load(ea.benchmark_yaml("clawbench-prorl-openclaw:latest"))
    assert doc["name"] == "clawbench"
    assert (
        doc["base_images"]["browser"]["official_image"]
        == "clawbench-prorl-openclaw:latest"
    )


def test_task_json_schema(one_case) -> None:
    task_dir, task = one_case
    spec = ea.build_task_json(task_dir.name, task, base_image="img", eval_timeout=180)
    # SForge contract fields
    assert spec["base_image"] == "browser"
    assert spec["cwd"] == "/app"
    assert spec["submit_paths"] == ["evidence/"]
    assert spec["game_mode"] is False
    # task_id is lowercase_underscore
    assert spec["task_id"] == spec["task_id"].lower()
    assert "-" not in spec["task_id"]
    # judge -> structured_json, maximize, score_first, calls our judge
    j = spec["judge"]
    assert j["parser"] == "structured_json"
    assert j["score_direction"] == "maximize"
    assert j["selection"] == "score_first"
    assert "clawbench-edgebench-judge" in j["eval_cmd"]
    assert "/app/evidence" in j["eval_cmd"]
    # work prompt tells the agent to submit evidence once
    assert "sforge-submit" in spec["work"]["agent_query"]
    assert "evidence/interception.json" in spec["work"]["agent_query"]


def test_write_benchmark_layout(one_case, tmp_path: Path) -> None:
    task_dir, task = one_case
    written = ea.write_benchmark(
        [(task_dir, task)], tmp_path, base_image="img", eval_timeout=180
    )
    tasks_dir = tmp_path / "tasks"
    assert (tasks_dir / "BENCHMARK.yaml").is_file()
    assert len(written) == 1
    spec = json.loads(written[0].read_text())
    sid = spec["task_id"]
    # per-task specs staged for both containers
    assert (tasks_dir / sid / "specs" / "task.json").is_file()
    assert (tasks_dir / sid / "specs" / "eval-schema.json").is_file()
