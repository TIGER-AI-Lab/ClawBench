"""WebVoyager task loader (#190)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from clawbench.adapters import (
    AdapterError,
    ScoringLayer,
    get_adapter,
    registered_sources,
)
from clawbench.adapters import cli as sources_cli
from clawbench.adapters.webvoyager import (
    DEFAULT_TIME_LIMIT_MINUTES,
    SUBMIT_EVAL_SCHEMA,
    SUBMIT_FOOTER,
)
from clawbench.utils.paths import ASSET_ROOT

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "webvoyager"
TASK_SCHEMA = ASSET_ROOT / "test-cases" / "task.schema.json"
CLAW_EVAL = ASSET_ROOT / "test-cases" / "claw-eval"


def test_webvoyager_is_registered() -> None:
    assert "webvoyager" in registered_sources()
    adapter = get_adapter("webvoyager")
    assert adapter.upstream == "https://github.com/MinorJerry/WebVoyager"
    assert not adapter.bundled


def test_loads_a_checkout_and_maps_every_field() -> None:
    tasks = get_adapter("webvoyager").load(FIXTURE)

    assert [t.task_id for t in tasks] == [
        "examplerecipes--0",
        "examplerecipes--1",
        "examplemaps--0",
    ]
    first = tasks[0]
    assert first.source == "webvoyager"
    assert first.source_id == "ExampleRecipes--0"
    assert first.url == "https://recipes.example.test/"
    assert first.category == "ExampleRecipes"
    assert first.time_limit == DEFAULT_TIME_LIMIT_MINUTES
    assert first.instruction.startswith("Find a vegetarian lasagna recipe")
    assert first.instruction.endswith(SUBMIT_FOOTER)
    assert first.metadata["sites_involved"] == ["recipes.example.test"]
    assert first.metadata["description"] == first.instruction.removesuffix(
        SUBMIT_FOOTER
    )


def test_tasks_run_through_the_answer_submit_interception_path() -> None:
    """WebVoyager has no write request to intercept; the answer submit is it."""
    task = get_adapter("webvoyager").load(FIXTURE)[0]

    assert task.eval_schema == SUBMIT_EVAL_SCHEMA
    assert task.supports(ScoringLayer.SUBMISSION_INTERCEPT)
    assert task.supports(ScoringLayer.LLM_JUDGE_ONLY)
    assert not task.supports(ScoringLayer.STEP_TRACE_REPLAY)
    assert "http://127.0.0.1:7878/submit" in task.instruction


def test_submit_contract_matches_the_shipped_claw_eval_port() -> None:
    """Same endpoint the runtime server and judge already handle for claw-eval."""
    sample = next(CLAW_EVAL.glob("*/task.json"))
    claw_eval = json.loads(sample.read_text(encoding="utf-8"))

    assert claw_eval["eval_schema"] == SUBMIT_EVAL_SCHEMA
    assert "http://127.0.0.1:7878/submit" in claw_eval["instruction"]


def test_reference_answers_become_labelled_judge_context() -> None:
    tasks = {t.source_id: t for t in get_adapter("webvoyager").load(FIXTURE)}

    with_ref = tasks["ExampleRecipes--0"]
    assert with_ref.judge_context["reference_solution"] == (
        "[golden] World's Best Vegetarian Lasagna\n"
        "[possible] Spinach and Ricotta Lasagna"
    )
    assert "golden" in with_ref.judge_context["rubric"]
    assert with_ref.warnings == ()

    without = tasks["ExampleRecipes--1"]
    assert without.judge_context == {}
    (warning,) = without.warnings
    assert warning.field_name == "judge_context"
    assert "no reference answer" in warning.message
    assert warning.fallback == "judge on question alone"


def test_missing_start_url_is_a_warning_not_a_drop() -> None:
    task = {t.source_id: t for t in get_adapter("webvoyager").load(FIXTURE)}[
        "ExampleMaps--0"
    ]

    assert task.url is None
    assert task.metadata["sites_involved"] == []
    assert any(w.field_name == "url" for w in task.warnings)


def test_missing_reference_file_warns_once_per_task(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "WebVoyager_data.jsonl").write_text(
        '{"web_name": "X", "id": "X--0", "ques": "Q?", "web": "https://x.test/"}\n'
    )

    (task,) = get_adapter("webvoyager").load(tmp_path)

    (warning,) = task.warnings
    assert "reference_answer.json not found" in warning.message


def test_accepts_a_direct_path_to_the_jsonl() -> None:
    tasks = get_adapter("webvoyager").load(FIXTURE / "data" / "WebVoyager_data.jsonl")

    assert len(tasks) == 3
    # References are still found relative to the data file's checkout.
    assert tasks[0].judge_context


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("", "holds no tasks"),
        ("{not json}\n", "not JSON"),
        ("[]\n", "expected an object"),
        (
            '{"web_name": "X", "id": "X--0", "web": "https://x.test/"}\n',
            "`id` and `ques`",
        ),
    ],
)
def test_malformed_checkouts_fail_with_a_location(
    tmp_path: Path, body: str, match: str
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "WebVoyager_data.jsonl").write_text(body, encoding="utf-8")

    with pytest.raises(AdapterError, match=match):
        get_adapter("webvoyager").load(tmp_path)


def test_not_a_checkout_says_what_was_expected(tmp_path: Path) -> None:
    with pytest.raises(AdapterError, match="WebVoyager_data.jsonl"):
        get_adapter("webvoyager").load(tmp_path)


def test_rendered_task_json_satisfies_the_runner_contract() -> None:
    task = get_adapter("webvoyager").load(FIXTURE)[0]
    rendered = task.to_task_json()

    schema = json.loads(TASK_SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(
        {
            "type": "object",
            "required": schema["required"],
            "properties": {
                key: schema["properties"][key]
                for key in ("instruction", "eval_schema", "time_limit", "judge_context")
            },
        }
    )
    assert list(validator.iter_errors(rendered)) == []
    assert rendered["metadata"]["source"] == "webvoyager"
    assert rendered["metadata"]["source_id"] == "ExampleRecipes--0"


def test_sources_cli_lists_webvoyager_tasks(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        sources_cli.main(["cases", "webvoyager", "--path", str(FIXTURE), "--json"]) == 0
    )

    rows = json.loads(capsys.readouterr().out)
    assert [row["source_id"] for row in rows] == [
        "ExampleRecipes--0",
        "ExampleRecipes--1",
        "ExampleMaps--0",
    ]
    assert rows[0]["scoring_layers"] == ["submission_intercept", "llm_judge_only"]
