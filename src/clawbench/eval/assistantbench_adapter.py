"""``clawbench-assistantbench-adapt``: import AssistantBench as a ClawBench suite (#188).

`AssistantBench <https://huggingface.co/datasets/AssistantBench/AssistantBench>`_
(Yoran et al., `arXiv:2407.15711 <https://arxiv.org/abs/2407.15711>`_) is 214 live-web
tasks chosen to be realistic and time-consuming: multi-step research, comparison
shopping, "which gyms near me have classes before 7AM". It scores a free-text final
answer against gold, with no interceptable final request.

ClawBench already has a home for that shape, and it is in ``main``: the ``claw-eval``
port tells the agent to submit its final answer at the runtime server's
``http://127.0.0.1:7878/submit`` form, which ``POST``s to ``/api/task-submit``; the
task's ``eval_schema`` targets that endpoint, so Stage-1 becomes "did the agent
commit to an answer", and Stage-2 judges the submitted answer against
``judge_context``. This adapter reuses that path verbatim, so an AssistantBench task
runs through the ordinary pipeline with **no runner changes** and produces the
standard five-layer bundle. ``tests/test_assistantbench_adapter.py`` pins the submit
contract against a bundled ``claw-eval`` task so the two cannot drift apart.

The deterministic upstream answer metric is the third score, and it lives in
:mod:`clawbench.eval.assistantbench_score`, run after the batch:

.. code-block:: bash

    clawbench-assistantbench-adapt --input assistantbench-validation.jsonl \\
        --output-dir test-cases/assistantbench
    clawbench-batch --models <m> --cases-dir test-cases/assistantbench --all-cases
    clawbench-assistantbench-score test-output/<m> \\
        --gold test-cases/assistantbench/assistantbench-gold.json

Field mapping
-------------

======================================  ==========================================
ClawBench                               AssistantBench
======================================  ==========================================
``metadata.source_task_id``             ``id`` (verbatim; the real key)
``metadata.task_id``                    ``600000 + n``, n over ids in sorted order
``metadata.class``                      ``metadata``'s expertise field, else ``general``
``metadata.sites_involved``             hostnames parsed out of ``gold_url``
``instruction``                         ``task`` + answer-format block + submit footer
``eval_schema``                         fixed ``POST /api/task-submit``
``time_limit``                          ``--time-limit`` (default 30, long-horizon)
``judge_context.reference_solution``    ``answer`` + ``explanation`` + ``gold_url``
``judge_context.rubric``                grading rubric derived from the answer shape
======================================  ==========================================

Gold answers never enter the container. ``run.py`` mounts only the ``eval_schema``
block (as ``/eval-schema.json``); ``metadata`` and ``judge_context`` stay host-side,
where the judge and the scorer read them.

Input
-----
A local export of the dataset, as ``.jsonl`` (one row per line) or ``.json``
(a list of rows). The dataset is Apache-2.0 and small:

.. code-block:: bash

    hf download AssistantBench/AssistantBench --repo-type dataset --local-dir ./assistantbench

Rows on the held-out test split ship without an ``answer``. Those tasks are still
emitted so they can be run, but they carry no gold: they are left out of the gold
sidecar and the adapter reports how many, since the deterministic metric cannot
score them locally.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

# The claw-eval answer-submit contract, reused verbatim. The runtime server serves
# the form at /submit and it POSTs to /api/task-submit; see
# src/clawbench/runtime/runtime-server/server.py.
SUBMIT_URL_PATTERN = "/api/task-submit"
SUBMIT_METHOD = "POST"
SUBMIT_FOOTER = (
    "\n\n---\n"
    "When you have completed the research and are ready to give the final answer, "
    "open http://127.0.0.1:7878/submit in the browser and submit your final answer "
    "there. Submit only after you are satisfied that the answer fulfills the task."
)

ANSWER_FORMAT_BLOCK = (
    "\n\nAnswer format. Your submission is graded by exact comparison against a "
    "reference answer, so submit the answer itself and nothing else: no preamble, "
    "no explanation, no source list, no units beyond what the question asks for.\n"
    "- If the question asks for a single number, submit just that number.\n"
    "- If the question asks for a short phrase or name, submit just that phrase.\n"
    "- If the question asks for several items each having several attributes, "
    "submit a JSON list of objects, one object per item, using the attribute names "
    "the question uses.\n"
    "- If you could not determine the answer, submit an empty answer rather than a "
    "guess."
)

DEFAULT_TIME_LIMIT = 30.0
TASK_ID_BASE = 600000

_COMMON_INFO = {
    "email_credentials": "credentials to use the assigned disposable email account",
    "user_info": "alex_green_personal_info.json; the dummy user's personal information",
    "user_resume": "PDF resume with disposable email account injected",
}

_SLUG_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "many",
    "me",
    "much",
    "my",
    "of",
    "on",
    "or",
    "please",
    "that",
    "the",
    "their",
    "there",
    "they",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "will",
    "with",
    "you",
    "your",
}


class AdapterError(Exception):
    """A checkout or export that does not have the shape this adapter reads."""


def _slug(text: str, *, max_words: int = 4) -> str:
    """Short readable slug from the task text, stopwords dropped."""
    words = [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]
    kept = [w for w in words if w not in _SLUG_STOPWORDS][:max_words]
    if not kept:
        kept = words[:max_words]
    return "-".join(kept) or "task"


def case_name(source_id: str, task_text: str) -> str:
    """Stable, readable directory name: ``ab-<id prefix>-<slug>``.

    Keyed on the source id rather than the row's position, so re-exporting the
    dataset in a different order does not rename every case.
    """
    prefix = re.sub(r"[^a-z0-9]+", "", str(source_id).lower())[:12] or "unknown"
    return f"ab-{prefix}-{_slug(task_text)}"


def _expertise(row: dict[str, Any]) -> str:
    """The expertise field out of the row's ``metadata``, which is a JSON string."""
    raw = row.get("metadata")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return "general"
    if not isinstance(raw, dict):
        return "general"
    for key in ("field", "expertise", "expertise_field", "domain", "category"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return (
                re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
                or "general"
            )
    return "general"


def _sites(row: dict[str, Any]) -> list[str]:
    """Hostnames referenced by ``gold_url``, deduplicated, order preserved."""
    raw = row.get("gold_url")
    if not isinstance(raw, str) or not raw.strip():
        return ["web"]
    sites: list[str] = []
    for token in re.split(r"[\s,;]+", raw):
        if not token:
            continue
        candidate = token if "://" in token else f"https://{token}"
        host = (urlparse(candidate).hostname or "").lower().removeprefix("www.")
        if host and host not in sites:
            sites.append(host)
    return sites or ["web"]


def _rubric(gold_answer: str | None) -> str:
    """Grading rubric for Stage-2, shaped by what the gold answer looks like."""
    base = (
        "Grade the agent's submitted answer against the reference answer below.\n"
        "- Match only when the submitted answer conveys the same facts as the "
        "reference. Formatting, ordering and wording may differ.\n"
        "- A number is a match when it agrees with the reference to the precision "
        "the question implies; a different quantity, unit or scale is a mismatch.\n"
        "- A list answer is a match only when it covers the reference items without "
        "inventing extras.\n"
        "- An answer that is hedged, partial, or unsupported by the reference is a "
        "mismatch.\n"
        "- An empty submission is a mismatch."
    )
    if not gold_answer:
        return (
            base
            + "\n\nNo reference answer ships with this split, so judge whether the "
            "submitted answer fully and plausibly addresses every part of the "
            "question, and treat any unsupported claim as a mismatch."
        )
    return base


def _reference(row: dict[str, Any], gold_answer: str | None) -> str:
    parts: list[str] = []
    if gold_answer:
        parts.append(f"Reference answer:\n{gold_answer}")
    explanation = row.get("explanation")
    if isinstance(explanation, str) and explanation.strip():
        parts.append(f"How the reference answer was obtained:\n{explanation.strip()}")
    gold_url = row.get("gold_url")
    if isinstance(gold_url, str) and gold_url.strip():
        parts.append(f"Sources used for the reference answer:\n{gold_url.strip()}")
    return "\n\n".join(parts)


def build_task(
    row: dict[str, Any], task_id: int, *, time_limit: float
) -> dict[str, Any]:
    """One AssistantBench row to one ClawBench ``task.json`` dict."""
    source_id = row.get("id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise AdapterError("row has no 'id'")
    question = row.get("task")
    if not isinstance(question, str) or not question.strip():
        raise AdapterError(f"row {source_id}: has no 'task' text")

    raw_answer = row.get("answer")
    gold_answer = raw_answer.strip() if isinstance(raw_answer, str) else None
    gold_answer = gold_answer or None

    difficulty = (
        row.get("difficulty") if isinstance(row.get("difficulty"), str) else None
    )
    split = row.get("set") if isinstance(row.get("set"), str) else None

    task: dict[str, Any] = {
        "metadata": {
            "task_id": task_id,
            "metaclass": "assistantbench",
            "class": _expertise(row),
            "description": question.strip().replace("\n", " ")[:160],
            "sites_involved": _sites(row),
            "platform": "assistantbench",
            "common_info": dict(_COMMON_INFO),
            "source": "assistantbench",
            "source_task_id": source_id,
            "source_split": split,
            "source_difficulty": difficulty,
            "source_has_gold_answer": gold_answer is not None,
        },
        "instruction": question.strip() + ANSWER_FORMAT_BLOCK + SUBMIT_FOOTER,
        "eval_schema": {
            "url_pattern": SUBMIT_URL_PATTERN,
            "method": SUBMIT_METHOD,
        },
        "time_limit": float(time_limit),
    }

    reference = _reference(row, gold_answer)
    judge_context: dict[str, Any] = {"rubric": _rubric(gold_answer)}
    if reference:
        judge_context["reference_solution"] = reference
    task["judge_context"] = judge_context
    return task


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Read an AssistantBench export: ``.jsonl`` lines, or ``.json`` holding a list."""
    if not path.is_file():
        raise AdapterError(f"input file not found: {path}")
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    if path.suffix == ".jsonl":
        for line_no, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as e:
                raise AdapterError(f"{path}:{line_no}: not valid JSON: {e}") from e
            if not isinstance(parsed, dict):
                raise AdapterError(f"{path}:{line_no}: expected an object")
            rows.append(parsed)
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise AdapterError(f"{path}: not valid JSON: {e}") from e
        if isinstance(parsed, dict) and isinstance(parsed.get("rows"), list):
            parsed = parsed["rows"]
        if not isinstance(parsed, list):
            raise AdapterError(f"{path}: expected a list of rows")
        for index, item in enumerate(parsed):
            if not isinstance(item, dict):
                raise AdapterError(f"{path}: row {index} is not an object")
            rows.append(item)
    if not rows:
        raise AdapterError(f"{path}: no rows")
    return rows


def select_rows(
    rows: Iterable[dict[str, Any]],
    *,
    split: str | None = None,
    difficulty: str | None = None,
    ids: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Filter and order rows. Ordering is by id, so task numbering is stable."""
    selected = []
    for row in rows:
        if split and str(row.get("set") or "").lower() != split.lower():
            continue
        if (
            difficulty
            and str(row.get("difficulty") or "").lower() != difficulty.lower()
        ):
            continue
        if ids and str(row.get("id")) not in ids:
            continue
        selected.append(row)
    selected.sort(key=lambda r: str(r.get("id")))
    if limit is not None:
        selected = selected[:limit]
    return selected


def write_suite(
    rows: list[dict[str, Any]], output_dir: Path, *, time_limit: float
) -> dict[str, Any]:
    """Write one task directory per row plus the gold sidecar. Returns a summary."""
    output_dir.mkdir(parents=True, exist_ok=True)
    gold: dict[str, dict[str, Any]] = {}
    written: list[str] = []
    without_gold: list[str] = []
    seen: dict[str, str] = {}

    for index, row in enumerate(rows):
        task = build_task(row, TASK_ID_BASE + index, time_limit=time_limit)
        name = case_name(str(row["id"]), str(row["task"]))
        if name in seen:
            raise AdapterError(
                f"case-name collision: {row['id']!r} and {seen[name]!r} both "
                f"produce {name!r}"
            )
        seen[name] = str(row["id"])

        case_dir = output_dir / name
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "task.json").write_text(
            json.dumps(task, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        written.append(name)

        if task["metadata"]["source_has_gold_answer"]:
            gold[name] = {
                "id": row["id"],
                "answer": row["answer"],
                "difficulty": row.get("difficulty"),
            }
        else:
            without_gold.append(name)

    gold_path = output_dir / "assistantbench-gold.json"
    gold_path.write_text(
        json.dumps(gold, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        "tasks": len(written),
        "with_gold": len(gold),
        "without_gold": without_gold,
        "output_dir": output_dir,
        "gold_path": gold_path,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawbench-assistantbench-adapt",
        description=(
            "Convert an AssistantBench export into a ClawBench task suite that runs "
            "through the existing answer-submit interception path."
        ),
    )
    p.add_argument(
        "--input",
        type=Path,
        required=True,
        help="AssistantBench export (.jsonl, or .json holding a list of rows)",
    )
    p.add_argument(
        "--output-dir", type=Path, required=True, help="Suite directory to write"
    )
    p.add_argument(
        "--split", default=None, help="Keep only rows whose 'set' matches (e.g. dev)"
    )
    p.add_argument(
        "--difficulty", default=None, help="Keep only rows of this difficulty"
    )
    p.add_argument("--ids", default="", help="Comma-separated source ids to keep")
    p.add_argument("--limit", type=int, default=None, help="Cap the number of tasks")
    p.add_argument(
        "--time-limit",
        type=float,
        default=DEFAULT_TIME_LIMIT,
        help=(
            "Per-task wall-clock minutes. AssistantBench tasks are long-horizon by "
            f"design; default {DEFAULT_TIME_LIMIT:g}"
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.time_limit < 1:
        print("ERROR: --time-limit must be at least 1 minute", file=sys.stderr)
        return 1
    try:
        rows = load_rows(args.input)
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    requested = {token.strip() for token in args.ids.split(",") if token.strip()}
    selected = select_rows(
        rows,
        split=args.split,
        difficulty=args.difficulty,
        ids=requested or None,
        limit=args.limit,
    )
    if not selected:
        print("ERROR: no rows matched the given filters", file=sys.stderr)
        return 1

    try:
        summary = write_suite(selected, args.output_dir, time_limit=args.time_limit)
    except (AdapterError, OSError) as e:
        print(f"ERROR: failed to write suite: {e}", file=sys.stderr)
        return 1

    print(f"Wrote {summary['tasks']} task(s) to {summary['output_dir']}")
    print(f"Gold answers for {summary['with_gold']} task(s) -> {summary['gold_path']}")
    if summary["without_gold"]:
        print(
            f"WARNING: {len(summary['without_gold'])} task(s) ship no gold answer and "
            "cannot be scored by clawbench-assistantbench-score; the LLM judge still "
            "grades them against the question.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
