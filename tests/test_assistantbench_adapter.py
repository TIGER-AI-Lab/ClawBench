"""Tests for the AssistantBench task-suite adapter (#188).

Fixtures here are synthetic rows in the upstream file shape, deliberately not
upstream content: the adapter is a schema mapping, and the mapping is what these
tests pin. The one thing checked against real repository data is the answer-submit
contract, which is pinned against a bundled claw-eval task so the two ports of
that path cannot drift apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from clawbench.eval import assistantbench_adapter as aba
from clawbench.eval import assistantbench_score as abs_score
from clawbench.utils.paths import asset_path


ROW = {
    "id": "a1b2c3d4e5f6a7b8",
    "set": "dev",
    "task": "Which gyms near Dolores Park have fitness classes before 7AM?",
    "answer": '{"name": "Iron Works", "opens": "05:30"}\n{"name": "Pier Fit", "opens": "06:00"}',
    "gold_url": "https://www.ironworks.example/schedule https://pierfit.example/classes",
    "explanation": "Checked the class timetable on each gym site.",
    "metadata": '{"duplication_status": "unique", "field": "Health and Fitness"}',
    "difficulty": "Hard",
}

ROW_NO_GOLD = {
    "id": "ffffffffffffffff",
    "set": "test",
    "task": "How many bridges cross the Charles River?",
    "answer": "",
    "gold_url": "",
    "explanation": "",
    "metadata": "{}",
    "difficulty": "Medium",
}


@pytest.fixture(scope="module")
def task_schema() -> Draft202012Validator:
    schema_path = asset_path("test-cases", "task.schema.json")
    if not schema_path.is_file():
        pytest.skip("bundled task.schema.json not available")
    return Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def claw_eval_task() -> dict:
    """A bundled claw-eval task: the reference implementation of answer mode."""
    cases = sorted(asset_path("test-cases", "claw-eval").glob("*/task.json"))
    if not cases:
        pytest.skip("no bundled claw-eval cases")
    return json.loads(cases[0].read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Field mapping
# --------------------------------------------------------------------------


def test_build_task_maps_every_field() -> None:
    task = aba.build_task(ROW, 600000, time_limit=30)
    meta = task["metadata"]
    assert meta["task_id"] == 600000
    assert meta["metaclass"] == "assistantbench"
    assert meta["platform"] == "assistantbench"
    assert meta["class"] == "health-and-fitness"
    assert meta["source_task_id"] == ROW["id"]
    assert meta["source_split"] == "dev"
    assert meta["source_difficulty"] == "Hard"
    assert meta["source_has_gold_answer"] is True
    assert meta["sites_involved"] == ["ironworks.example", "pierfit.example"]
    assert task["instruction"].startswith(ROW["task"])
    assert task["time_limit"] == 30.0


def test_build_task_requires_an_id_and_a_question() -> None:
    with pytest.raises(aba.AdapterError, match="no 'id'"):
        aba.build_task({"task": "x"}, 1, time_limit=30)
    with pytest.raises(aba.AdapterError, match="no 'task' text"):
        aba.build_task({"id": "abc"}, 1, time_limit=30)


def test_class_falls_back_to_general_for_unusable_metadata() -> None:
    for metadata in ("not json", "{}", None, "[]"):
        task = aba.build_task({**ROW, "metadata": metadata}, 1, time_limit=30)
        assert task["metadata"]["class"] == "general"


def test_sites_involved_defaults_to_web_without_gold_urls() -> None:
    task = aba.build_task(ROW_NO_GOLD, 1, time_limit=30)
    assert task["metadata"]["sites_involved"] == ["web"]


def test_sites_involved_deduplicates_and_drops_the_www_prefix() -> None:
    row = {**ROW, "gold_url": "https://www.a.example/x, https://a.example/y; b.example"}
    assert aba.build_task(row, 1, time_limit=30)["metadata"]["sites_involved"] == [
        "a.example",
        "b.example",
    ]


# --------------------------------------------------------------------------
# The answer-submit contract, pinned against claw-eval
# --------------------------------------------------------------------------


def test_eval_schema_matches_the_bundled_claw_eval_contract(
    claw_eval_task: dict,
) -> None:
    task = aba.build_task(ROW, 1, time_limit=30)
    assert task["eval_schema"] == claw_eval_task["eval_schema"]
    assert task["eval_schema"] == {"url_pattern": "/api/task-submit", "method": "POST"}


def test_submit_footer_matches_the_bundled_claw_eval_wording(
    claw_eval_task: dict,
) -> None:
    """Same wording, so a harness tuned for one suite behaves the same on the other."""
    task = aba.build_task(ROW, 1, time_limit=30)
    assert task["instruction"].endswith(aba.SUBMIT_FOOTER)
    assert aba.SUBMIT_FOOTER.strip() in claw_eval_task["instruction"]


def test_instruction_tells_the_agent_how_to_shape_its_answer() -> None:
    """The deterministic metric compares strings, so answer shape has to be stated."""
    instruction = aba.build_task(ROW, 1, time_limit=30)["instruction"]
    assert "JSON list of objects" in instruction
    assert "empty answer rather than a" in instruction


# --------------------------------------------------------------------------
# The gold answer must never reach the agent
# --------------------------------------------------------------------------


def test_gold_answer_stays_out_of_the_agent_facing_fields() -> None:
    """run.py mounts only eval_schema; judge_context and metadata stay host-side."""
    task = aba.build_task(ROW, 1, time_limit=30)
    agent_facing = json.dumps(
        {"instruction": task["instruction"], "eval_schema": task["eval_schema"]}
    )
    assert "Iron Works" not in agent_facing
    assert "05:30" not in agent_facing
    assert "ironworks.example" not in agent_facing
    assert "Iron Works" in task["judge_context"]["reference_solution"]


def test_judge_context_carries_the_reference_and_a_rubric() -> None:
    context = aba.build_task(ROW, 1, time_limit=30)["judge_context"]
    assert "Reference answer:" in context["reference_solution"]
    assert ROW["explanation"] in context["reference_solution"]
    assert ROW["gold_url"] in context["reference_solution"]
    assert "Grade the agent's submitted answer" in context["rubric"]


def test_rubric_says_so_when_no_reference_answer_ships() -> None:
    context = aba.build_task(ROW_NO_GOLD, 1, time_limit=30)["judge_context"]
    assert "No reference answer ships with this split" in context["rubric"]
    assert "reference_solution" not in context


# --------------------------------------------------------------------------
# Schema conformance
# --------------------------------------------------------------------------


def test_generated_tasks_validate_against_task_schema(task_schema) -> None:
    for row in (ROW, ROW_NO_GOLD):
        task = aba.build_task(row, 600000, time_limit=30)
        errors = sorted(task_schema.iter_errors(task), key=lambda e: list(e.path))
        assert errors == [], [
            f"/{'/'.join(map(str, e.path))}: {e.message}" for e in errors
        ]


def test_generated_tasks_pass_the_runner_validator() -> None:
    from clawbench.runner.run_support.task import validate_task_data

    task = aba.build_task(ROW, 600000, time_limit=30)
    assert validate_task_data(task, Path("task.json")) is task


# --------------------------------------------------------------------------
# Case naming
# --------------------------------------------------------------------------


def test_case_name_is_readable_and_keyed_on_the_source_id() -> None:
    name = aba.case_name(ROW["id"], ROW["task"])
    assert name.startswith("ab-a1b2c3d4e5f6-")
    assert "gyms" in name
    # Stable regardless of where the row sat in the export.
    assert name == aba.case_name(ROW["id"], ROW["task"])


def test_case_name_survives_an_id_with_punctuation() -> None:
    assert aba.case_name("AB/12-34", "Find the tallest building").startswith(
        "ab-ab1234-"
    )


def test_case_name_handles_an_all_stopword_question() -> None:
    assert aba.case_name("abc", "what is it") == "ab-abc-what-is-it"


# --------------------------------------------------------------------------
# Row loading and selection
# --------------------------------------------------------------------------


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def test_load_rows_reads_jsonl_and_json(tmp_path: Path) -> None:
    assert (
        len(aba.load_rows(_write_jsonl(tmp_path / "a.jsonl", [ROW, ROW_NO_GOLD]))) == 2
    )
    (tmp_path / "b.json").write_text(json.dumps([ROW]), encoding="utf-8")
    assert len(aba.load_rows(tmp_path / "b.json")) == 1
    (tmp_path / "c.json").write_text(json.dumps({"rows": [ROW]}), encoding="utf-8")
    assert len(aba.load_rows(tmp_path / "c.json")) == 1


def test_load_rows_reports_where_the_file_went_wrong(tmp_path: Path) -> None:
    bad = tmp_path / "a.jsonl"
    bad.write_text(json.dumps(ROW) + "\nnot json\n", encoding="utf-8")
    with pytest.raises(aba.AdapterError, match=r":2: not valid JSON"):
        aba.load_rows(bad)

    (tmp_path / "b.jsonl").write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(aba.AdapterError, match=r":1: expected an object"):
        aba.load_rows(tmp_path / "b.jsonl")

    (tmp_path / "c.json").write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(aba.AdapterError, match="expected a list of rows"):
        aba.load_rows(tmp_path / "c.json")

    (tmp_path / "d.jsonl").write_text("\n\n", encoding="utf-8")
    with pytest.raises(aba.AdapterError, match="no rows"):
        aba.load_rows(tmp_path / "d.jsonl")

    with pytest.raises(aba.AdapterError, match="input file not found"):
        aba.load_rows(tmp_path / "missing.jsonl")


def test_select_rows_filters_and_orders_by_id() -> None:
    rows = [ROW, ROW_NO_GOLD]
    assert [r["id"] for r in aba.select_rows(rows)] == [ROW["id"], ROW_NO_GOLD["id"]]
    assert [r["id"] for r in aba.select_rows(rows, split="test")] == [ROW_NO_GOLD["id"]]
    assert [r["id"] for r in aba.select_rows(rows, difficulty="hard")] == [ROW["id"]]
    assert [r["id"] for r in aba.select_rows(rows, ids={ROW["id"]})] == [ROW["id"]]
    assert len(aba.select_rows(rows, limit=1)) == 1


def test_select_rows_numbering_is_independent_of_export_order() -> None:
    forwards = aba.select_rows([ROW, ROW_NO_GOLD])
    backwards = aba.select_rows([ROW_NO_GOLD, ROW])
    assert [r["id"] for r in forwards] == [r["id"] for r in backwards]


# --------------------------------------------------------------------------
# Writing the suite
# --------------------------------------------------------------------------


def test_write_suite_emits_tasks_and_the_gold_sidecar(tmp_path: Path) -> None:
    out = tmp_path / "suite"
    summary = aba.write_suite([ROW, ROW_NO_GOLD], out, time_limit=30)
    assert summary["tasks"] == 2
    assert summary["with_gold"] == 1

    cases = sorted(p.parent.name for p in out.glob("*/task.json"))
    assert len(cases) == 2

    gold = json.loads((out / "assistantbench-gold.json").read_text(encoding="utf-8"))
    assert list(gold) == [aba.case_name(ROW["id"], ROW["task"])]
    assert gold[aba.case_name(ROW["id"], ROW["task"])]["difficulty"] == "Hard"
    # The row without a gold answer is emitted as a task but is not scorable.
    assert (
        aba.case_name(ROW_NO_GOLD["id"], ROW_NO_GOLD["task"]) in summary["without_gold"]
    )


def test_write_suite_assigns_task_ids_from_the_reserved_block(tmp_path: Path) -> None:
    out = tmp_path / "suite"
    aba.write_suite(aba.select_rows([ROW, ROW_NO_GOLD]), out, time_limit=30)
    ids = sorted(
        json.loads(p.read_text(encoding="utf-8"))["metadata"]["task_id"]
        for p in out.glob("*/task.json")
    )
    assert ids == [aba.TASK_ID_BASE, aba.TASK_ID_BASE + 1]


def test_write_suite_refuses_a_case_name_collision(tmp_path: Path) -> None:
    twin = {**ROW, "id": ROW["id"]}
    with pytest.raises(aba.AdapterError, match="case-name collision"):
        aba.write_suite([ROW, twin], tmp_path / "suite", time_limit=30)


def test_written_tasks_are_discoverable_by_the_batch_runner_glob(
    tmp_path: Path,
) -> None:
    """clawbench-batch finds cases with a plain */task.json search."""
    out = tmp_path / "suite"
    aba.write_suite([ROW, ROW_NO_GOLD], out, time_limit=30)
    assert len(list(out.glob("*/task.json"))) == 2
    # The sidecar sits beside the cases, so it is never mistaken for one.
    assert (out / "assistantbench-gold.json").is_file()
    assert not (out / "assistantbench-gold.json").is_dir()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_writes_a_suite(tmp_path: Path, capsys) -> None:
    src = _write_jsonl(tmp_path / "ab.jsonl", [ROW, ROW_NO_GOLD])
    out = tmp_path / "suite"
    assert aba.main(["--input", str(src), "--output-dir", str(out)]) == 0
    captured = capsys.readouterr()
    assert "Wrote 2 task(s)" in captured.out
    assert "1 task(s) ship no gold answer" in captured.err
    task = json.loads(next(out.glob("*/task.json")).read_text(encoding="utf-8"))
    assert task["time_limit"] == aba.DEFAULT_TIME_LIMIT


def test_cli_honours_filters_and_time_limit(tmp_path: Path) -> None:
    src = _write_jsonl(tmp_path / "ab.jsonl", [ROW, ROW_NO_GOLD])
    out = tmp_path / "suite"
    code = aba.main(
        [
            "--input",
            str(src),
            "--output-dir",
            str(out),
            "--split",
            "dev",
            "--time-limit",
            "12",
        ]
    )
    assert code == 0
    tasks = list(out.glob("*/task.json"))
    assert len(tasks) == 1
    assert json.loads(tasks[0].read_text(encoding="utf-8"))["time_limit"] == 12.0


def test_cli_errors_on_bad_input(tmp_path: Path) -> None:
    src = _write_jsonl(tmp_path / "ab.jsonl", [ROW])
    out = tmp_path / "suite"
    assert (
        aba.main(["--input", str(tmp_path / "nope.jsonl"), "--output-dir", str(out)])
        == 1
    )
    assert (
        aba.main(["--input", str(src), "--output-dir", str(out), "--split", "nothing"])
        == 1
    )
    assert (
        aba.main(["--input", str(src), "--output-dir", str(out), "--time-limit", "0"])
        == 1
    )


# --------------------------------------------------------------------------
# Adapter and scorer agree end to end
# --------------------------------------------------------------------------


def test_adapted_suite_scores_through_the_scorer(tmp_path: Path) -> None:
    """Adapt a row, fake the run its agent would produce, score it: 1.0."""
    suite = tmp_path / "suite"
    aba.write_suite([ROW], suite, time_limit=30)
    case = aba.case_name(ROW["id"], ROW["task"])

    run_dir = tmp_path / "out" / "run-1"
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "run-meta.json").write_text(
        json.dumps({"test_case": case}), encoding="utf-8"
    )
    (run_dir / "data" / "interception.json").write_text(
        json.dumps(
            {
                "intercepted": True,
                "request": {
                    "url": "http://127.0.0.1:7878/api/task-submit",
                    "method": "POST",
                    "body": {"answer": ROW["answer"]},
                },
            }
        ),
        encoding="utf-8",
    )

    gold = abs_score.load_gold(suite / "assistantbench-gold.json")
    records, unmatched = abs_score.score_runs([run_dir], gold)
    assert unmatched == []
    assert records[0]["score"] == pytest.approx(1.0)
    assert abs_score.aggregate(records)["accuracy"] == 100.0
    assert abs_score.aggregate(records)["accuracy_by_difficulty"]["Hard"] == 100.0
