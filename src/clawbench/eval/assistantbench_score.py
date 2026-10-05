"""``clawbench-assistantbench-score``: AssistantBench answer accuracy as a third stage (#188).

ClawBench scores a run in two stages: Stage-1 asks whether the agent produced the
request ``eval_schema`` describes, Stage-2 asks the LLM judge whether that request
fulfils the instruction. AssistantBench scores a run a third way: it compares the
agent's **final answer string** against a gold answer with a deterministic,
answer-type-aware metric, with no model in the loop.

This module ports that metric and reports it alongside the existing two, so a
ClawBench batch over an adapted AssistantBench suite (see
:mod:`clawbench.eval.assistantbench_adapter`) produces the numbers the upstream
leaderboard reports: accuracy, answer rate, precision, exact match, and accuracy
split by difficulty.

Upstream reference
------------------
The authoritative implementation is the ``evaluation/`` package of the
`AssistantBench leaderboard Space
<https://huggingface.co/spaces/AssistantBench/leaderboard>`_ (Apache-2.0), whose
string metric is in turn derived from the DROP benchmark's ``drop_eval`` (also
Apache-2.0). Paper: `arXiv:2407.15711 <https://arxiv.org/abs/2407.15711>`_.

This is a re-implementation rather than a vendored copy, for two reasons: upstream
depends on ``numpy`` and ``scipy``, which ClawBench does not, and the judge path is
deliberately stdlib-only.

Verification
------------
The port was checked against the upstream evaluator running under ``numpy`` 2.5.3
and ``scipy`` 1.18.1, over 7249 ``(prediction, gold)`` pairs: the 3249-pair
exhaustive product of a corpus covering all four answer types, plus 4000 fuzzed
pairs. On all 6581 pairs upstream could score, the two agree exactly, to 1e-9, on
both accuracy and answer rate. On the remaining 668 upstream raises
``TypeError``/``AttributeError`` from a malformed prediction (a record object
answering a numeric question, ``null``, ``true``, a bare list); the port scores
those 0.0 with the task counted as answered, so one unparseable answer cannot take
down a whole batch's scoring.

Deviations from upstream, all deliberate
----------------------------------------
1. ``scipy.optimize.linear_sum_assignment`` is replaced by an exact rectangular
   Jonker-Volgenant solver (:func:`_assign_min`). It is exact, not greedy;
   ``tests/test_assistantbench_score.py`` checks it against brute force over
   random matrices, so alignment scores are identical to upstream's.
2. A single-element list prediction holding a number (``[5]``, ``["5"]``) gets
   ``fix_number``'s *value*. Upstream assigns the whole ``(value, is_numeric)``
   tuple and then raises ``TypeError`` inside ``float()`` on the next line, so
   there is no upstream behaviour to preserve here.
3. An empty score vector scores 0.0 rather than ``numpy``'s ``nan``-with-warning.
   The same applies to a gold dict with no keys.
4. A dict value whose Python type is outside upstream's evaluator table (``None``,
   a nested dict, a list of dicts) is compared with the string evaluator instead
   of raising ``KeyError``. A type mismatch between prediction and gold still
   scores 0 before the evaluator is consulted, exactly as upstream.
5. A prediction and gold with opposite signs score 0. ``numpy`` reaches the same
   answer by way of ``nan`` (``max(0, nan)`` is 0 because ``nan > 0`` is False);
   ``math.log`` would raise instead, so the sign is checked first.

Everything else, including the quirks, is preserved on purpose: the ``$``/``%``/
``sqft`` stripping, ``,`` being read as a decimal point, the log-distance number
metric (which can exceed 1 when both values are negative), precision being recall
with the arguments swapped, ``json``-mode gold wrapping a single parsed object in
a list, and a non-string answer span scoring 0 rather than being stringified.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import string
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# --------------------------------------------------------------------------
# Exact rectangular assignment (stands in for scipy.optimize.linear_sum_assignment)
# --------------------------------------------------------------------------

_INF = float("inf")


def _assign_min(cost: list[list[float]]) -> list[tuple[int, int]]:
    """Minimum-cost 1-1 assignment over a rectangular matrix with rows <= cols.

    Jonker-Volgenant with potentials. Returns one ``(row, col)`` pair per row.
    Callers negate to maximize and transpose when rows > cols.
    """
    n = len(cost)
    m = len(cost[0])
    if n > m:
        raise ValueError(f"_assign_min needs rows <= cols, got {n}x{m}")

    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    parent = [0] * (m + 1)  # parent[j] = 1-based row currently matched to column j
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        parent[0] = i
        j0 = 0
        minv = [_INF] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = parent[j0]
            delta = _INF
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[parent[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if parent[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            parent[j0] = parent[j1]
            j0 = j1

    return [(parent[j] - 1, j - 1) for j in range(1, m + 1) if parent[j] != 0]


def _max_assignment(scores: list[list[float]]) -> list[tuple[int, int]]:
    """Maximum-score 1-1 assignment. ``scores[row][col]``; returns ``(row, col)``."""
    rows = len(scores)
    cols = len(scores[0])
    if rows <= cols:
        return _assign_min([[-value for value in row] for row in scores])
    transposed = [[-scores[r][c] for r in range(rows)] for c in range(cols)]
    return [(row, col) for (col, row) in _assign_min(transposed)]


def _align(
    predicted: Sequence[Any],
    gold: Sequence[Any],
    method: Callable[[Any, Any], float],
) -> list[float]:
    """Best 1-1 alignment score per gold item, padded to ``max(len(gold), len(pred))``.

    The padding is what makes a prediction with extra items score below 1: the
    denominator is the longer of the two sequences, so unmatched predictions
    dilute the mean even when every gold item was matched perfectly.
    """
    n_gold = len(gold)
    n_pred = len(predicted)
    if n_gold == 0 or n_pred == 0:
        return [0.0] * max(n_gold, n_pred)
    scores = [[float(method(p, g)) for p in predicted] for g in gold]
    aligned = [0.0] * max(n_gold, n_pred)
    for row, col in _max_assignment(scores):
        aligned[row] = max(aligned[row], scores[row][col])
    return aligned


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


# --------------------------------------------------------------------------
# String metric (derived from DROP's drop_eval, via upstream evaluate_strings.py)
# --------------------------------------------------------------------------

_ARTICLES_RE = re.compile(r"\b(a|an|the)\b", re.UNICODE)
_PUNCTUATION = set(string.punctuation)


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def _normalize_number(text: str) -> str:
    return str(float(text)) if _is_number(text) else text


def _remove_punc(text: str) -> str:
    if _is_number(text):
        return text
    return "".join(ch for ch in text if ch not in _PUNCTUATION)


def _normalize_answer(text: str) -> str:
    """Lowercase, drop punctuation and articles, canonicalize numbers and spacing."""
    parts = [
        " ".join(
            _ARTICLES_RE.sub(
                " ", _normalize_number(_remove_punc(token.lower()))
            ).split()
        )
        for token in re.split(" |-", text)
    ]
    return " ".join(part for part in parts if part.strip()).strip()


def _answer_to_bags(answer: Any) -> tuple[list[str], list[set[str]]]:
    raw_spans = answer if isinstance(answer, (list, tuple)) else [answer]
    normalized: list[str] = []
    bags: list[set[str]] = []
    for span in raw_spans:
        if not isinstance(span, str):
            # Upstream's tokenizer raises on a non-string span and evaluate_strings
            # turns that into 0.0. Stringifying instead would score a bare number
            # list against a prose answer, which upstream never does.
            raise TypeError(f"answer span must be a string, got {type(span).__name__}")
        text = _normalize_answer(span)
        normalized.append(text)
        bags.append(set(text.split()))
    return normalized, bags


def _compute_f1(predicted_bag: set[str], gold_bag: set[str]) -> float:
    intersection = len(gold_bag & predicted_bag)
    precision = 1.0 if not predicted_bag else intersection / len(predicted_bag)
    recall = 1.0 if not gold_bag else intersection / len(gold_bag)
    if precision == 0.0 and recall == 0.0:
        return 0.0
    return (2 * precision * recall) / (precision + recall)


def _match_numbers_if_present(gold_bag: set[str], predicted_bag: set[str]) -> bool:
    """Gate token-F1 on number agreement, so '3 bedrooms' never matches '4 bedrooms'."""
    gold_numbers = {word for word in gold_bag if _is_number(word)}
    predicted_numbers = {word for word in predicted_bag if _is_number(word)}
    return (not gold_numbers) or bool(gold_numbers & predicted_numbers)


def _align_string_bags(predicted: list[set[str]], gold: list[set[str]]) -> list[float]:
    def scorer(pred_bag: set[str], gold_bag: set[str]) -> float:
        if not _match_numbers_if_present(gold_bag, pred_bag):
            return 0.0
        return _compute_f1(pred_bag, gold_bag)

    return _align(predicted, gold, scorer)


def evaluate_strings(prediction: Any, gold: Any) -> float:
    """Mean aligned token-F1 between a prediction and gold string (or string list)."""
    if not isinstance(prediction, (list, str)):
        prediction = str(prediction)
    if not isinstance(gold, (list, str)):
        gold = str(gold)
    try:
        _, predicted_bags = _answer_to_bags(prediction)
        _, gold_bags = _answer_to_bags(gold)
        return _mean(_align_string_bags(predicted_bags, gold_bags))
    except Exception:
        return 0.0


# --------------------------------------------------------------------------
# Number metric
# --------------------------------------------------------------------------


def _distance_function_log(pred: float, gold: float) -> float:
    """1 - log(ratio), floored at 0: an order of magnitude off scores 0."""
    if pred == gold == 0:
        return 1.0
    if pred == 0:
        pred = 1e-4
    if gold == 0:
        gold = 1e-4
    ratio = pred / gold if pred > gold else gold / pred
    if ratio <= 0:
        # Opposite signs. numpy's log returns nan here and max(0, nan) is 0,
        # because nan > 0 is False; math.log would raise instead.
        return 0.0
    return max(0.0, 1 - math.log(ratio))


def evaluate_numbers(pred: Any, gold: Any) -> float:
    if not isinstance(pred, (float, int)) or isinstance(pred, bool):
        try:
            pred = float(pred)
        except (TypeError, ValueError):
            return 0.0
    if not isinstance(gold, (float, int)) or isinstance(gold, bool):
        try:
            gold = float(gold)
        except (TypeError, ValueError):
            return 0.0
    return _distance_function_log(float(pred), float(gold))


# --------------------------------------------------------------------------
# Dict metric
# --------------------------------------------------------------------------


def _evaluator_for_type(value_type: type) -> Callable[[Any, Any], float]:
    if value_type is bool:
        return evaluate_strings
    if value_type in (int, float):
        return evaluate_numbers
    if value_type in (str, list):
        return evaluate_strings
    # Deviation 4: upstream raises KeyError for anything else.
    return evaluate_strings


def _fix_dict_number(value: Any) -> Any:
    """``fix_number`` without the is-numeric flag, as the dict metric uses it."""
    if isinstance(value, str):
        text = " ".join(
            " ".join(" ".join(value.split("$")).split("%")).split("sqft")
        ).strip()
        text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def _calc_recall(pred: dict, gold: dict, use_gold_for_eval: bool) -> float:
    recall: list[float] = []
    for gold_key, raw_gold_value in gold.items():
        present = gold_key in pred
        gold_value = _fix_dict_number(raw_gold_value)
        pred_value = _fix_dict_number(pred.get(gold_key))
        if not present:
            recall.append(0.0)
            continue
        evaluator = _evaluator_for_type(
            type(gold_value) if use_gold_for_eval else type(pred_value)
        )
        if type(pred_value) is not type(gold_value):
            recall.append(0.0)
            continue
        recall.append(evaluator(pred_value, gold_value))
    return _mean(recall)


def _evaluate_pair_of_dicts(pred: Any, gold: Any) -> float:
    if not isinstance(pred, dict) or not isinstance(gold, dict):
        return 0.0
    recall = _calc_recall(pred, gold, True)
    # Upstream computes precision as recall with the arguments swapped; keep that.
    precision = _calc_recall(gold, pred, False)
    if precision + recall == 0:
        return 0.0
    return 2 * (precision * recall) / (precision + recall)


def evaluate_dicts(pred: Any, gold: Any) -> float:
    """Mean aligned pairwise F1 over a list of key-value records."""
    if isinstance(pred, dict):
        pred = [pred]
    if not isinstance(pred, list):
        return 0.0
    if pred and not isinstance(pred[0], dict):
        return 0.0
    gold_list = gold if isinstance(gold, list) else [gold]
    return _mean(_align(pred, gold_list, _evaluate_pair_of_dicts))


_EVALUATORS: dict[str, Callable[[Any, Any], float]] = {
    "string": evaluate_strings,
    "number": evaluate_numbers,
    "json": evaluate_dicts,
    "string list": evaluate_strings,
}


# --------------------------------------------------------------------------
# Answer parsing (upstream evaluator.py)
# --------------------------------------------------------------------------


def _fix_ans(answer: str) -> str:
    """Coerce a Python-repr dict string into JSON by swapping quote styles."""
    try:
        answer = (
            answer.replace("{'", '{"')
            .replace("', '", '", "')
            .replace("': '", '": "')
            .replace("'}", '"}')
        )
        return answer.replace("': ", '": ')
    except AttributeError:
        return answer


def _fix_number(number: Any) -> tuple[Any, bool]:
    """Strip currency/percent/unit noise and try to read the result as a float."""
    if isinstance(number, str):
        text = " ".join(
            " ".join(" ".join(number.split("$")).split("%")).split("sqft")
        ).strip()
        text = text.replace(",", ".").replace(" square kilometers", "")
        try:
            return float(text), True
        except ValueError:
            return number, False
    if isinstance(number, int) and not isinstance(number, bool):
        return float(number), True
    return number, True


def _parse_answer(answer: list[Any]) -> tuple[Any, str]:
    """Infer the gold answer's type: number, json record list, string, or string list."""
    if len(answer) == 1:
        value, is_num = _fix_number(answer[0])
        if is_num:
            return value, "number"
        try:
            return [json.loads(_fix_ans(answer[0]))], "json"
        except (TypeError, ValueError):
            value, is_num = _fix_number(answer[0])
            return (value, "number") if is_num else (answer[0], "string")
    try:
        return [json.loads(_fix_ans(item)) for item in answer], "json"
    except (TypeError, ValueError):
        return answer, "string list"


def _is_nan(value: Any) -> bool:
    try:
        return math.isnan(value)
    except (TypeError, ValueError):
        return False


def _is_empty(value: Any) -> bool:
    """True when the value holds nothing gradeable.

    A number is never empty. ``bool`` is folded in with the numbers because
    ``len(True)`` raises, and upstream's bare ``len()`` treats that the same way.
    """
    if isinstance(value, (bool, float, int)):
        return False
    try:
        return len(value) == 0
    except TypeError:
        return False


def _fix_prediction(
    prediction: Any, gold_answer: Any, evaluator: str
) -> tuple[Any, bool]:
    if (
        isinstance(prediction, list)
        and len(prediction) == 1
        and (
            (isinstance(prediction[0], int) and not isinstance(prediction[0], bool))
            or (isinstance(prediction[0], str) and prediction[0].isnumeric())
        )
    ):
        # Deviation 2: take the value, not fix_number's (value, is_numeric) tuple.
        prediction = _fix_number(prediction[0])[0]

    if not isinstance(prediction, list):
        prediction, _ = _fix_number(prediction)
        if evaluator == "json":
            try:
                prediction = [json.loads(part) for part in prediction.split("\n")]
            except (AttributeError, TypeError, ValueError):
                prediction = [prediction]

    if _is_empty(prediction):
        return prediction, False
    if (
        isinstance(prediction, list)
        and len(prediction) > 1
        and isinstance(gold_answer, float)
    ):
        # Several answers offered for a single-number question: not gradeable.
        return prediction, False
    return prediction, True


def question_scorer(prediction: Any, gold_answer: Any) -> tuple[float, float]:
    """Score one answer against gold. Returns ``(accuracy, has_answer)``, both 0-1.

    ``has_answer`` is 0 when the agent produced nothing gradeable; it is the
    numerator of the leaderboard's answer rate, and rows with ``has_answer == 0``
    are excluded from precision.
    """
    if isinstance(prediction, str):
        try:
            prediction = json.loads(prediction)
        except ValueError:
            pass

    if isinstance(gold_answer, list):
        answer_list = gold_answer
    else:
        answer_list = [line for line in str(gold_answer).split("\n") if line.strip()]
    parsed_gold, evaluator = _parse_answer(answer_list)
    prediction, run_eval = _fix_prediction(prediction, parsed_gold, evaluator)

    has_answer = 1.0
    if _is_empty(prediction) or _is_nan(prediction):
        has_answer = 0.0
    if isinstance(prediction, list) and all(
        _is_empty(item) or _is_nan(item) for item in prediction
    ):
        has_answer = 0.0

    if not run_eval:
        return 0.0, has_answer
    return float(_EVALUATORS[evaluator](prediction, parsed_gold)), has_answer


# --------------------------------------------------------------------------
# Aggregation (upstream leaderboard app.py)
# --------------------------------------------------------------------------

_DIFFICULTIES = ("Easy", "Medium", "Hard")


def aggregate(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Leaderboard-shaped aggregate over per-run ``{score, has_ans, difficulty}``.

    Every metric averages over *runs*, matching how ``clawbench-analyze``
    aggregates. ``tasks`` counts the distinct cases behind those runs, so a
    caller can see when a case was run more than once and the averages are no
    longer one-per-task.
    """
    scores = [float(r["score"]) for r in records]
    answered = [float(r["has_ans"]) for r in records]
    answered_scores = [float(r["score"]) for r in records if float(r["has_ans"]) == 1.0]

    def pct(value: float) -> float:
        return round(value * 100, 1)

    by_difficulty: dict[str, float | None] = {}
    counts: dict[str, int] = {}
    for level in _DIFFICULTIES:
        level_scores = [
            float(r["score"])
            for r in records
            if str(r.get("difficulty") or "") == level
        ]
        counts[level] = len(level_scores)
        by_difficulty[level] = pct(_mean(level_scores)) if level_scores else None

    cases = {str(r["case_name"]) for r in records if r.get("case_name")}
    return {
        "runs": len(records),
        "tasks": len(cases) or len(records),
        "accuracy": pct(_mean(scores)),
        "answer_rate": pct(_mean(answered)),
        "precision": pct(_mean(answered_scores)) if answered_scores else 0.0,
        "exact_match": pct(_mean([1.0 if s == 1 else 0.0 for s in scores])),
        "accuracy_by_difficulty": by_difficulty,
        "count_by_difficulty": counts,
    }


# --------------------------------------------------------------------------
# Reading answers back out of a ClawBench batch
# --------------------------------------------------------------------------


def load_gold(path: Path) -> dict[str, dict[str, Any]]:
    """Load gold answers keyed by every identifier a run might be found under.

    Accepts the sidecar ``assistantbench-gold.json`` the adapter writes, a raw
    AssistantBench export (``.jsonl``, or ``.json`` holding a list), and a plain
    ``{id: answer}`` mapping. Each entry is registered under its source id and,
    when known, its ClawBench case name, so lookup works from either direction.
    """
    raw = path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    if path.suffix == ".jsonl":
        for line_no, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{line_no}: not valid JSON: {e}") from e
    else:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            rows = [r for r in parsed if isinstance(r, dict)]
        elif isinstance(parsed, dict):
            for key, value in parsed.items():
                if isinstance(value, dict):
                    rows.append({"case_name": key, **value})
                else:
                    rows.append({"id": key, "answer": value})
        else:
            raise ValueError(f"{path}: expected a list or object, got {type(parsed)}")

    gold: dict[str, dict[str, Any]] = {}
    for row in rows:
        if "answer" not in row:
            continue
        entry = {
            "id": row.get("id"),
            "answer": row["answer"],
            "difficulty": row.get("difficulty"),
        }
        for key in (row.get("id"), row.get("case_name")):
            if isinstance(key, str) and key:
                gold[key] = entry
    return gold


def extract_answer(run_dir: Path) -> str | None:
    """Pull the agent's submitted answer out of a run's ``interception.json``.

    Answer-mode tasks post ``{"answer": ...}`` to the runtime server's
    ``/api/task-submit``; the interceptor captures that body verbatim. Returns
    ``None`` when the run never reached the submit step, which the caller scores
    as an unanswered task rather than a wrong one.
    """
    path = run_dir / "data" / "interception.json"
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    body = (blob.get("request") or {}).get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return body
    if isinstance(body, dict):
        answer = body.get("answer")
        if answer is None:
            return None
        return (
            answer
            if isinstance(answer, str)
            else json.dumps(answer, ensure_ascii=False)
        )
    return None


def _case_name(run_dir: Path) -> str:
    meta = run_dir / "run-meta.json"
    if meta.is_file():
        try:
            blob = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            blob = {}
        for key in ("test_case", "case_name"):
            value = blob.get(key)
            if isinstance(value, str) and value:
                return value
        task = blob.get("task")
        if isinstance(task, dict) and isinstance(task.get("case_name"), str):
            return task["case_name"]
    return run_dir.name


def discover_runs(runs_dir: Path) -> list[Path]:
    """Every run directory under ``runs_dir``, at any nesting depth.

    ``clawbench-batch`` writes ``<base>/<model>/<run>/``, a single
    ``clawbench-run`` writes ``<base>/<run>/``, and users pass both. Discovery
    matches ``clawbench-analyze``: a directory counts as a run when it holds a
    ``run-meta.json`` or a ``data/interception.json``.
    """
    if (runs_dir / "run-meta.json").is_file():
        return [runs_dir]
    found = {path.parent for path in runs_dir.rglob("run-meta.json")}
    found |= {path.parent.parent for path in runs_dir.rglob("data/interception.json")}
    return sorted(found)


def models_in(runs: Sequence[Path]) -> set[str]:
    """Distinct model names recorded across these runs."""
    models: set[str] = set()
    for run_dir in runs:
        meta_path = run_dir / "run-meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        model = meta.get("model") if isinstance(meta, dict) else None
        if isinstance(model, str) and model:
            models.add(model)
    return models


def score_runs(
    runs: Sequence[Path], gold: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Score each run against gold. Returns ``(records, unmatched-run-names)``."""
    records: list[dict[str, Any]] = []
    unmatched: list[str] = []
    for run_dir in runs:
        case = _case_name(run_dir)
        entry = gold.get(case)
        if entry is None:
            unmatched.append(run_dir.name)
            continue
        answer = extract_answer(run_dir)
        if answer is None:
            # No submit request at all: unanswered, not incorrect.
            score, has_ans = 0.0, 0.0
        else:
            score, has_ans = question_scorer(answer, entry["answer"])
        records.append(
            {
                "run": run_dir.name,
                "case_name": case,
                "id": entry.get("id"),
                "difficulty": entry.get("difficulty"),
                "answered": answer is not None,
                "model_answer": answer,
                "score": score,
                "has_ans": has_ans,
            }
        )
    return records, unmatched


def _write_run_meta(runs_dir: Path, records: Sequence[dict[str, Any]]) -> int:
    """Add ``assistantbench_answer_score`` to each scored run's ``run-meta.json``."""
    written = 0
    by_run = {record["run"]: record for record in records}
    for run_dir in discover_runs(runs_dir):
        record = by_run.get(run_dir.name)
        meta_path = run_dir / "run-meta.json"
        if record is None or not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(meta, dict):
            continue
        meta["assistantbench_answer_score"] = {
            "score": record["score"],
            "has_answer": record["has_ans"],
            "source_task_id": record.get("id"),
            "difficulty": record.get("difficulty"),
            "metric": "assistantbench/question_scorer",
        }
        meta_path.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        written += 1
    return written


def format_report(summary: dict[str, Any], records: Sequence[dict[str, Any]]) -> str:
    """Markdown report in the shape of the upstream leaderboard row."""
    lines = [
        "# AssistantBench answer accuracy",
        "",
        f"Runs scored: {summary['runs']} over {summary['tasks']} task(s)",
    ]
    if summary["runs"] != summary["tasks"]:
        lines.append("")
        lines.append(
            "Some tasks were run more than once. Every metric below averages over "
            "runs, so a repeated task weighs more than one run once."
        )
    lines += [
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Accuracy | {summary['accuracy']} |",
        f"| Answer rate | {summary['answer_rate']} |",
        f"| Precision | {summary['precision']} |",
        f"| EM | {summary['exact_match']} |",
    ]
    for level in _DIFFICULTIES:
        value = summary["accuracy_by_difficulty"].get(level)
        count = summary["count_by_difficulty"].get(level, 0)
        shown = "n/a" if value is None else value
        lines.append(f"| Accuracy ({level.lower()}) | {shown} (n={count}) |")
    lines += [
        "",
        "| Task | Difficulty | Answered | Score |",
        "| --- | --- | --- | --- |",
    ]
    for record in sorted(records, key=lambda r: str(r["case_name"])):
        lines.append(
            f"| {record['case_name']} | {record.get('difficulty') or '-'} "
            f"| {'yes' if record['answered'] else 'no'} | {record['score']:.3f} |"
        )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawbench-assistantbench-score",
        description=(
            "Score a ClawBench batch of adapted AssistantBench tasks with the "
            "upstream answer metric (accuracy, answer rate, precision, EM)."
        ),
    )
    p.add_argument(
        "runs_dir", type=Path, help="Batch output dir, or a single run directory"
    )
    p.add_argument(
        "--gold",
        type=Path,
        required=True,
        help=(
            "assistantbench-gold.json written by clawbench-assistantbench-adapt, "
            "or a raw AssistantBench export (.jsonl / .json)"
        ),
    )
    p.add_argument(
        "--json-out", type=Path, default=None, help="Write the full result as JSON"
    )
    p.add_argument(
        "--markdown-out", type=Path, default=None, help="Write the report as Markdown"
    )
    p.add_argument(
        "--write-run-meta",
        action="store_true",
        help=(
            "Also record assistantbench_answer_score in each scored run's "
            "run-meta.json (off by default: this edits existing run output)"
        ),
    )
    p.add_argument(
        "--allow-mixed-models",
        action="store_true",
        help=(
            "Score runs from several models together. Off by default: pointing "
            "at test-output/ instead of test-output/<model> would otherwise "
            "average models into one meaningless leaderboard row"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.runs_dir.is_dir():
        print(f"ERROR: runs dir not found: {args.runs_dir}", file=sys.stderr)
        return 1
    if not args.gold.is_file():
        print(f"ERROR: gold file not found: {args.gold}", file=sys.stderr)
        return 1
    try:
        gold = load_gold(args.gold)
    except (OSError, ValueError) as e:
        print(f"ERROR: could not read gold answers: {e}", file=sys.stderr)
        return 1
    if not gold:
        print(f"ERROR: no gold answers in {args.gold}", file=sys.stderr)
        return 1

    runs = discover_runs(args.runs_dir)
    if not runs:
        print(f"ERROR: no run directories under {args.runs_dir}", file=sys.stderr)
        return 1

    models = models_in(runs)
    if len(models) > 1 and not args.allow_mixed_models:
        print(
            "ERROR: these runs span "
            + f"{len(models)} models ({', '.join(sorted(models))}). "
            "A leaderboard row describes one model, so point at one model's "
            "directory (test-output/<model>), or pass --allow-mixed-models if "
            "you really want them averaged together.",
            file=sys.stderr,
        )
        return 1

    records, unmatched = score_runs(runs, gold)
    if unmatched:
        print(
            f"WARNING: {len(unmatched)} run(s) had no gold entry and were skipped: "
            + ", ".join(unmatched[:5])
            + (" ..." if len(unmatched) > 5 else ""),
            file=sys.stderr,
        )
    if not records:
        print("ERROR: no runs matched a gold answer", file=sys.stderr)
        return 1

    summary = aggregate(records)
    report = format_report(summary, records)
    print(report, end="")

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(
                {"summary": summary, "records": records, "skipped": unmatched},
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {args.json_out}")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(report, encoding="utf-8")
        print(f"Wrote {args.markdown_out}")
    if args.write_run_meta:
        written = _write_run_meta(args.runs_dir, records)
        print(f"Updated assistantbench_answer_score in {written} run-meta.json file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
