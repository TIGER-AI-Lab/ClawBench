"""Tests for the AssistantBench answer metric and its batch scorer (#188).

The metric is a re-implementation of the upstream leaderboard's ``evaluation/``
package without numpy/scipy, so these tests do two things: pin the behaviours a
port could silently get wrong (the assignment solver, the answer-type dispatch,
the aggregation formulas) and pin the upstream quirks that look like bugs, so
nobody "fixes" them and drifts away from the published numbers.
"""

from __future__ import annotations

import itertools
import json
import math
import random
from pathlib import Path

import pytest

from clawbench.eval import assistantbench_score as abs_score


# --------------------------------------------------------------------------
# The assignment solver: exact, not greedy
# --------------------------------------------------------------------------


def _brute_force_max(scores: list[list[float]]) -> float:
    """Best achievable total over all 1-1 assignments, by exhaustive search."""
    rows = len(scores)
    cols = len(scores[0])
    best = 0.0
    if rows <= cols:
        for combo in itertools.permutations(range(cols), rows):
            best = max(best, sum(scores[r][c] for r, c in enumerate(combo)))
    else:
        for combo in itertools.permutations(range(rows), cols):
            best = max(best, sum(scores[r][c] for c, r in enumerate(combo)))
    return best


@pytest.mark.parametrize(
    "shape", [(1, 1), (2, 2), (3, 3), (2, 4), (4, 2), (1, 5), (5, 1), (4, 4)]
)
def test_max_assignment_matches_brute_force(shape: tuple[int, int]) -> None:
    rows, cols = shape
    rng = random.Random(f"{rows}x{cols}")
    for _ in range(40):
        scores = [[rng.random() for _ in range(cols)] for _ in range(rows)]
        pairs = abs_score._max_assignment(scores)
        total = sum(scores[r][c] for r, c in pairs)
        assert total == pytest.approx(_brute_force_max(scores), abs=1e-9)
        # One pair per row/column of the shorter dimension, no repeats.
        assert len(pairs) == min(rows, cols)
        assert len({r for r, _ in pairs}) == len(pairs)
        assert len({c for _, c in pairs}) == len(pairs)


def test_max_assignment_is_not_greedy() -> None:
    """The greedy pick (0.9 first) is worse than the optimal pairing."""
    scores = [[0.9, 0.8], [0.85, 0.0]]
    pairs = sorted(abs_score._max_assignment(scores))
    assert pairs == [(0, 1), (1, 0)]
    assert sum(scores[r][c] for r, c in pairs) == pytest.approx(1.65)


def test_assign_min_rejects_more_rows_than_columns() -> None:
    with pytest.raises(ValueError, match="rows <= cols"):
        abs_score._assign_min([[1.0], [1.0]])


def test_align_pads_to_the_longer_side() -> None:
    """Extra predictions dilute the mean; that is how over-answering is penalized."""
    aligned = abs_score._align(
        ["a", "b", "c"], ["a", "b"], lambda p, g: 1.0 if p == g else 0.0
    )
    assert aligned == [1.0, 1.0, 0.0]
    assert abs_score._align([], ["a"], lambda p, g: 1.0) == [0.0]
    assert abs_score._align(["a"], [], lambda p, g: 1.0) == [0.0]


# --------------------------------------------------------------------------
# question_scorer: answer-type dispatch
# --------------------------------------------------------------------------


def test_exact_string_answer() -> None:
    assert abs_score.question_scorer("Paris", "Paris") == (1.0, 1.0)


def test_string_answer_is_normalized_before_comparison() -> None:
    """Case, articles and punctuation are stripped, so these are the same answer."""
    score, has_ans = abs_score.question_scorer("the Eiffel Tower.", "Eiffel Tower")
    assert (score, has_ans) == (1.0, 1.0)


def test_partial_string_answer_scores_between_zero_and_one() -> None:
    score, has_ans = abs_score.question_scorer("Paris France", "Paris")
    assert has_ans == 1.0
    assert 0.0 < score < 1.0


def test_number_answer_exact_and_off_by_a_factor() -> None:
    assert abs_score.question_scorer("42", "42")[0] == pytest.approx(1.0)
    # The metric is 1 - log(ratio): double the right answer keeps partial credit.
    assert abs_score.question_scorer("84", "42")[0] == pytest.approx(1 - math.log(2))
    # An order of magnitude out earns nothing.
    assert abs_score.question_scorer("420", "42")[0] == 0.0


def test_number_answer_strips_currency_and_percent_noise() -> None:
    assert abs_score.question_scorer("$42", "42")[0] == pytest.approx(1.0)
    assert abs_score.question_scorer("42%", "42")[0] == pytest.approx(1.0)


def test_upstream_quirk_comma_is_read_as_a_decimal_point() -> None:
    """Pinned deliberately: upstream maps ',' to '.', so "1,000" parses as 1.0.

    This is not a bug in the port. Changing it would move our numbers away from
    the published leaderboard, so it stays until upstream changes it.
    """
    assert abs_score.question_scorer("1,000", "1000")[0] == 0.0
    assert abs_score.question_scorer("1000", "1000")[0] == pytest.approx(1.0)


def test_numbers_must_agree_for_string_answers_to_match() -> None:
    """Token F1 is gated on number agreement, so quantities cannot be fudged."""
    assert abs_score.question_scorer("3 bedrooms", "4 bedrooms")[0] == 0.0
    assert abs_score.question_scorer("4 bedrooms", "4 bedrooms")[0] == pytest.approx(
        1.0
    )


def test_json_record_answer_exact_match() -> None:
    gold = '{"name": "Alpha", "price": 10}\n{"name": "Beta", "price": 20}'
    assert abs_score.question_scorer(gold, gold)[0] == pytest.approx(1.0)


def test_json_record_answer_is_order_insensitive() -> None:
    gold = '{"name": "Alpha", "price": 10}\n{"name": "Beta", "price": 20}'
    swapped = '{"name": "Beta", "price": 20}\n{"name": "Alpha", "price": 10}'
    assert abs_score.question_scorer(swapped, gold)[0] == pytest.approx(1.0)


def test_json_record_answer_missing_field_loses_credit() -> None:
    gold = '{"name": "Alpha", "price": 10}'
    score, has_ans = abs_score.question_scorer('{"name": "Alpha"}', gold)
    assert has_ans == 1.0
    # recall 0.5 against precision 1.0 -> F1 2/3
    assert score == pytest.approx(2 / 3)


def test_json_record_answer_extra_record_dilutes_the_score() -> None:
    gold = '{"name": "Alpha", "price": 10}\n{"name": "Beta", "price": 20}'
    over = gold + '\n{"name": "Gamma", "price": 30}'
    assert abs_score.question_scorer(over, gold)[0] == pytest.approx(2 / 3)


def test_json_record_answer_wrong_value_type_scores_zero_for_that_field() -> None:
    """A type mismatch costs the field on both sides, so recall and precision drop.

    "price": "cheap" against a numeric 10 scores 0 for that field in both
    directions, giving recall 0.5, precision 0.5, F1 0.5 -- a harsher penalty
    than simply omitting the field, which keeps precision at 1.0.
    """
    gold = '{"name": "Alpha", "price": 10}'
    score, _ = abs_score.question_scorer('{"name": "Alpha", "price": "cheap"}', gold)
    assert score == pytest.approx(0.5)


def test_string_list_answer_matches_regardless_of_order() -> None:
    gold = "cat\ndog"
    assert abs_score.question_scorer('["dog", "cat"]', gold)[0] == pytest.approx(1.0)


def test_empty_answer_is_unanswered_not_wrong() -> None:
    """has_answer 0 keeps a non-attempt out of precision, which is the point of it."""
    assert abs_score.question_scorer("", "Paris") == (0.0, 0.0)
    assert abs_score.question_scorer("[]", "Paris") == (0.0, 0.0)


def test_single_element_numeric_list_does_not_raise() -> None:
    """Documented deviation 2: upstream raises TypeError on exactly this input."""
    assert abs_score.question_scorer("[5]", "5")[0] == pytest.approx(1.0)
    assert abs_score.question_scorer('["5"]', "5")[0] == pytest.approx(1.0)


def test_several_answers_for_a_single_number_question_are_not_gradeable() -> None:
    score, has_ans = abs_score.question_scorer('["5", "6", "7"]', "5")
    assert score == 0.0
    assert has_ans == 1.0


def test_evaluate_dicts_rejects_a_non_record_prediction() -> None:
    assert abs_score.evaluate_dicts(["not a dict"], [{"a": 1}]) == 0.0
    assert abs_score.evaluate_dicts("not a list", [{"a": 1}]) == 0.0


def test_evaluate_numbers_handles_unparseable_input() -> None:
    assert abs_score.evaluate_numbers("not a number", 5.0) == 0.0
    assert abs_score.evaluate_numbers(5.0, "not a number") == 0.0


def test_evaluate_numbers_handles_zero_on_either_side() -> None:
    assert abs_score.evaluate_numbers(0, 0) == 1.0
    assert abs_score.evaluate_numbers(0, 100) == 0.0


def test_opposite_signs_score_zero_without_raising() -> None:
    """numpy reaches 0 here through nan; math.log would raise, so the sign is checked.

    Caught by the differential run against the upstream evaluator.
    """
    assert abs_score.evaluate_numbers(42, -5) == 0.0
    assert abs_score.evaluate_numbers(-5, 42) == 0.0
    assert abs_score.question_scorer("42", "-5") == (0.0, 1.0)


def test_both_negative_keeps_upstream_ratio_behaviour() -> None:
    """Preserved quirk: with two negatives the metric can exceed 1."""
    assert abs_score.evaluate_numbers(-5, -10) == pytest.approx(1 - math.log(0.5))


def test_a_bare_number_list_does_not_match_a_prose_answer() -> None:
    """Upstream's tokenizer raises on a non-string span, which it scores as 0.

    Stringifying the spans instead would hand out token overlap that upstream
    never awards. Caught by the differential run.
    """
    assert abs_score.question_scorer("[1, 2, 3]", "3 bedrooms") == (0.0, 1.0)
    assert abs_score.evaluate_strings([1, 2, 3], "3 bedrooms") == 0.0


def test_an_ungradeable_answer_shape_scores_zero_instead_of_raising() -> None:
    """Upstream raises on each of these; a batch scorer cannot afford to."""
    for prediction in ('{"name": "Alpha"}', "null", "true", '["cat"]', "[5]"):
        score, has_ans = abs_score.question_scorer(prediction, "42")
        assert score == 0.0, prediction
        assert has_ans in (0.0, 1.0)


# --------------------------------------------------------------------------
# Aggregation matches the leaderboard's formulas
# --------------------------------------------------------------------------


def test_aggregate_matches_leaderboard_formulas() -> None:
    records = [
        {"score": 1.0, "has_ans": 1.0, "difficulty": "Easy", "case_name": "a"},
        {"score": 0.5, "has_ans": 1.0, "difficulty": "Hard", "case_name": "b"},
        {"score": 0.0, "has_ans": 0.0, "difficulty": "Hard", "case_name": "c"},
    ]
    summary = abs_score.aggregate(records)
    assert summary["runs"] == 3
    assert summary["tasks"] == 3
    assert summary["accuracy"] == 50.0
    assert summary["answer_rate"] == 66.7
    # Precision excludes the unanswered row: mean(1.0, 0.5).
    assert summary["precision"] == 75.0
    assert summary["exact_match"] == 33.3
    assert summary["accuracy_by_difficulty"] == {
        "Easy": 100.0,
        "Medium": None,
        "Hard": 25.0,
    }
    assert summary["count_by_difficulty"] == {"Easy": 1, "Medium": 0, "Hard": 2}


def test_aggregate_with_no_answered_tasks_reports_zero_precision() -> None:
    summary = abs_score.aggregate(
        [{"score": 0.0, "has_ans": 0.0, "difficulty": "Easy", "case_name": "a"}]
    )
    assert summary["precision"] == 0.0
    assert summary["answer_rate"] == 0.0


def test_aggregate_counts_runs_and_distinct_tasks_separately() -> None:
    """Averages are per run, as in clawbench-analyze; a repeat weighs twice."""
    records = [
        {"score": 1.0, "has_ans": 1.0, "difficulty": "Easy", "case_name": "a"},
        {"score": 0.0, "has_ans": 1.0, "difficulty": "Easy", "case_name": "a"},
    ]
    summary = abs_score.aggregate(records)
    assert summary["runs"] == 2
    assert summary["tasks"] == 1
    assert summary["accuracy"] == 50.0
    assert "run more than once" in abs_score.format_report(
        summary, [{**r, "answered": True} for r in records]
    )


# --------------------------------------------------------------------------
# Reading answers back out of a batch
# --------------------------------------------------------------------------


def _make_run(
    root: Path,
    name: str,
    case: str,
    answer: object | None,
    model: str = "glm-5.1",
) -> Path:
    run_dir = root / name
    (run_dir / "data").mkdir(parents=True)
    (run_dir / "run-meta.json").write_text(
        json.dumps({"test_case": case, "harness": "openclaw", "model": model}),
        encoding="utf-8",
    )
    if answer is not None:
        (run_dir / "data" / "interception.json").write_text(
            json.dumps(
                {
                    "intercepted": True,
                    "request": {
                        "url": "http://127.0.0.1:7878/api/task-submit",
                        "method": "POST",
                        "params": {},
                        "body": {"answer": answer},
                    },
                }
            ),
            encoding="utf-8",
        )
    return run_dir


def test_extract_answer_from_an_intercepted_submission(tmp_path: Path) -> None:
    run = _make_run(tmp_path, "run-1", "ab-aaa-x", "Paris")
    assert abs_score.extract_answer(run) == "Paris"


def test_extract_answer_handles_a_string_encoded_body(tmp_path: Path) -> None:
    run = _make_run(tmp_path, "run-1", "ab-aaa-x", "Paris")
    path = run / "data" / "interception.json"
    blob = json.loads(path.read_text(encoding="utf-8"))
    blob["request"]["body"] = json.dumps(blob["request"]["body"])
    path.write_text(json.dumps(blob), encoding="utf-8")
    assert abs_score.extract_answer(run) == "Paris"


def test_extract_answer_serializes_a_structured_answer(tmp_path: Path) -> None:
    run = _make_run(tmp_path, "run-1", "ab-aaa-x", [{"name": "Alpha"}])
    assert abs_score.extract_answer(run) == '[{"name": "Alpha"}]'


def test_extract_answer_is_none_when_the_agent_never_submitted(tmp_path: Path) -> None:
    run = _make_run(tmp_path, "run-1", "ab-aaa-x", None)
    assert abs_score.extract_answer(run) is None


def test_discover_runs_finds_batch_and_single_run_layouts(tmp_path: Path) -> None:
    batch = tmp_path / "batch" / "model-a"
    _make_run(batch, "run-1", "ab-aaa-x", "Paris")
    _make_run(batch, "run-2", "ab-bbb-y", "Rome")
    assert len(abs_score.discover_runs(tmp_path / "batch")) == 2
    assert len(abs_score.discover_runs(batch)) == 2
    assert abs_score.discover_runs(batch / "run-1") == [batch / "run-1"]


def test_score_runs_reports_unanswered_and_unmatched(tmp_path: Path) -> None:
    root = tmp_path / "out"
    _make_run(root, "run-1", "ab-aaa-x", "Paris")
    _make_run(root, "run-2", "ab-bbb-y", None)
    _make_run(root, "run-3", "ab-zzz-unknown", "Berlin")
    gold = {
        "ab-aaa-x": {"id": "aaa", "answer": "Paris", "difficulty": "Easy"},
        "ab-bbb-y": {"id": "bbb", "answer": "Rome", "difficulty": "Hard"},
    }
    records, unmatched = abs_score.score_runs(abs_score.discover_runs(root), gold)
    assert unmatched == ["run-3"]
    by_case = {r["case_name"]: r for r in records}
    assert by_case["ab-aaa-x"]["score"] == pytest.approx(1.0)
    assert by_case["ab-aaa-x"]["has_ans"] == 1.0
    # A run that never submitted is unanswered, so it cannot drag precision down.
    assert by_case["ab-bbb-y"]["answered"] is False
    assert by_case["ab-bbb-y"]["has_ans"] == 0.0


def test_score_runs_falls_back_to_the_directory_name(tmp_path: Path) -> None:
    root = tmp_path / "out"
    run = _make_run(root, "ab-aaa-x", "ab-aaa-x", "Paris")
    (run / "run-meta.json").unlink()
    gold = {"ab-aaa-x": {"id": "aaa", "answer": "Paris", "difficulty": "Easy"}}
    records, unmatched = abs_score.score_runs([run], gold)
    assert unmatched == []
    assert records[0]["score"] == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Gold loading accepts every shape a user will reach for
# --------------------------------------------------------------------------


def test_load_gold_from_the_adapter_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "assistantbench-gold.json"
    path.write_text(
        json.dumps(
            {"ab-aaa-x": {"id": "aaa", "answer": "Paris", "difficulty": "Easy"}}
        ),
        encoding="utf-8",
    )
    gold = abs_score.load_gold(path)
    # Registered under both the case name and the source id.
    assert gold["ab-aaa-x"]["answer"] == "Paris"
    assert gold["aaa"]["answer"] == "Paris"


def test_load_gold_from_a_raw_dataset_export(tmp_path: Path) -> None:
    path = tmp_path / "ab.jsonl"
    path.write_text(
        '{"id": "aaa", "answer": "Paris", "difficulty": "Easy"}\n'
        '{"id": "bbb", "answer": "Rome", "difficulty": "Hard"}\n',
        encoding="utf-8",
    )
    gold = abs_score.load_gold(path)
    assert set(gold) == {"aaa", "bbb"}
    assert gold["bbb"]["difficulty"] == "Hard"


def test_load_gold_from_a_plain_id_to_answer_mapping(tmp_path: Path) -> None:
    path = tmp_path / "gold.json"
    path.write_text(json.dumps({"aaa": "Paris"}), encoding="utf-8")
    assert abs_score.load_gold(path)["aaa"]["answer"] == "Paris"


def test_load_gold_reports_the_offending_line(tmp_path: Path) -> None:
    path = tmp_path / "ab.jsonl"
    path.write_text('{"id": "aaa", "answer": "Paris"}\nnot json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r":2: not valid JSON"):
        abs_score.load_gold(path)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _gold_file(tmp_path: Path) -> Path:
    path = tmp_path / "assistantbench-gold.json"
    path.write_text(
        json.dumps(
            {
                "ab-aaa-x": {"id": "aaa", "answer": "Paris", "difficulty": "Easy"},
                "ab-bbb-y": {"id": "bbb", "answer": "Rome", "difficulty": "Hard"},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_cli_scores_a_batch_and_writes_reports(tmp_path: Path, capsys) -> None:
    root = tmp_path / "out"
    _make_run(root, "run-1", "ab-aaa-x", "Paris")
    _make_run(root, "run-2", "ab-bbb-y", "Milan")
    gold = _gold_file(tmp_path)

    code = abs_score.main(
        [
            str(root),
            "--gold",
            str(gold),
            "--json-out",
            str(tmp_path / "score.json"),
            "--markdown-out",
            str(tmp_path / "score.md"),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "AssistantBench answer accuracy" in out

    blob = json.loads((tmp_path / "score.json").read_text(encoding="utf-8"))
    assert blob["summary"]["tasks"] == 2
    assert blob["summary"]["accuracy_by_difficulty"]["Easy"] == 100.0
    assert (
        (tmp_path / "score.md")
        .read_text(encoding="utf-8")
        .startswith("# AssistantBench")
    )


def test_cli_leaves_run_meta_alone_by_default(tmp_path: Path) -> None:
    root = tmp_path / "out"
    run = _make_run(root, "run-1", "ab-aaa-x", "Paris")
    gold = _gold_file(tmp_path)

    assert abs_score.main([str(root), "--gold", str(gold)]) == 0
    meta = json.loads((run / "run-meta.json").read_text(encoding="utf-8"))
    assert "assistantbench_answer_score" not in meta

    assert abs_score.main([str(root), "--gold", str(gold), "--write-run-meta"]) == 0
    meta = json.loads((run / "run-meta.json").read_text(encoding="utf-8"))
    assert meta["assistantbench_answer_score"]["score"] == pytest.approx(1.0)
    assert meta["assistantbench_answer_score"]["source_task_id"] == "aaa"
    # The third stage is additive: the existing keys survive.
    assert meta["test_case"] == "ab-aaa-x"


def test_cli_errors_on_missing_inputs(tmp_path: Path) -> None:
    gold = _gold_file(tmp_path)
    assert abs_score.main([str(tmp_path / "nope"), "--gold", str(gold)]) == 1
    (tmp_path / "empty").mkdir()
    assert (
        abs_score.main([str(tmp_path / "empty"), "--gold", str(tmp_path / "nope.json")])
        == 1
    )
    assert abs_score.main([str(tmp_path / "empty"), "--gold", str(gold)]) == 1


def test_cli_errors_when_no_run_matches_gold(tmp_path: Path) -> None:
    root = tmp_path / "out"
    _make_run(root, "run-1", "ab-unknown", "Paris")
    assert abs_score.main([str(root), "--gold", str(_gold_file(tmp_path))]) == 1


def test_cli_refuses_to_average_several_models_together(tmp_path: Path, capsys) -> None:
    """Pointing at test-output/ instead of test-output/<model> is an easy slip."""
    root = tmp_path / "out"
    _make_run(root / "model-a", "run-1", "ab-aaa-x", "Paris", model="model-a")
    _make_run(root / "model-b", "run-2", "ab-bbb-y", "Rome", model="model-b")
    gold = _gold_file(tmp_path)

    assert abs_score.main([str(root), "--gold", str(gold)]) == 1
    err = capsys.readouterr().err
    assert "span 2 models" in err
    assert "model-a, model-b" in err

    assert abs_score.main([str(root), "--gold", str(gold), "--allow-mixed-models"]) == 0


def test_discover_runs_reaches_arbitrary_nesting(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c" / "model"
    _make_run(deep, "run-1", "ab-aaa-x", "Paris")
    assert abs_score.discover_runs(tmp_path) == [deep / "run-1"]


def test_models_in_ignores_runs_without_usable_metadata(tmp_path: Path) -> None:
    root = tmp_path / "out"
    run = _make_run(root, "run-1", "ab-aaa-x", "Paris", model="model-a")
    broken = _make_run(root, "run-2", "ab-bbb-y", "Rome")
    (broken / "run-meta.json").write_text("not json", encoding="utf-8")
    missing = _make_run(root, "run-3", "ab-aaa-x", "Paris")
    (missing / "run-meta.json").unlink()
    assert abs_score.models_in([run, broken, missing]) == {"model-a"}
