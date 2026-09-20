"""WebVoyager (MinorJerry/WebVoyager) -> ClawBenchTask.

WebVoyager is the closest scope-peer of ClawBench: live websites, a
multimodal browser agent, and a question-per-task with a free-text answer.
Its tasks ship as one JSON object per line in ``data/WebVoyager_data.jsonl``,
with reference answers in ``data/reference_answer.json``.

Field mapping (``WebVoyager_data.jsonl`` -> ``ClawBenchTask``):

| Field             | Source                                                       |
|-------------------|--------------------------------------------------------------|
| ``task_id``       | ``id`` (e.g. ``Allrecipes--0``), lower-cased                 |
| ``source_id``     | ``id`` verbatim                                              |
| ``instruction``   | ``ques``, plus ClawBench's answer-submit footer              |
| ``url``           | ``web``                                                      |
| ``category``      | ``web_name``                                                 |
| ``time_limit``    | none upstream (step-bounded); ``DEFAULT_TIME_LIMIT_MINUTES`` |
| ``eval_schema``   | the local answer-submit endpoint (see below)                 |
| ``judge_context`` | ``reference_answer.json`` entry for this id, when present    |

WebVoyager scores by a screenshot-and-LLM judge over the agent's trajectory;
there is no final write request to intercept. ClawBench already handles this
shape for the claw-eval port: the instruction tells the agent to submit its
final answer at ``http://127.0.0.1:7878/submit``, the runtime server's
``POST /api/task-submit`` is the interception target, and the LLM judge scores
the submitted answer against the reference. So a WebVoyager task runs through
the ordinary Stage-1 + Stage-2 pipeline unchanged; the upstream screenshot
judge is a separate scoring passthrough not attempted here.

Reference answers come in two upstream grades, ``golden`` (exact) and
``possible`` (acceptable); both are handed to the judge, labelled, so it can
weigh them. A task whose reference is missing gets an ``AdapterWarning`` and
still loads — the judge then scores against the question alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from clawbench.adapters._base import AdapterBase, AdapterError, register
from clawbench.adapters.schema import AdapterWarning, ClawBenchTask, ScoringLayer

DATA_FILE = Path("data") / "WebVoyager_data.jsonl"
REFERENCE_FILE = Path("data") / "reference_answer.json"

# Upstream sets no per-task limit; its agent is bounded by a step count (15)
# rather than wall-clock. Ten minutes matches the claw-eval port's default.
DEFAULT_TIME_LIMIT_MINUTES = 10.0

# The same endpoint and wording the claw-eval port uses, so the runtime server
# and judge see WebVoyager submissions exactly as they see claw-eval ones.
SUBMIT_EVAL_SCHEMA = {"url_pattern": "/api/task-submit", "method": "POST"}
SUBMIT_FOOTER = (
    "\n\n---\n"
    "When you have completed the task and are ready to give the final answer, "
    "open http://127.0.0.1:7878/submit in the browser and submit your final "
    "answer there. Submit only after you are satisfied that the answer fulfills "
    "the task."
)


def _load_references(path: Path) -> dict[str, list[dict[str, Any]]]:
    """``{"<web_name>--<n>": [{"type": ..., "ans": ...}, ...]}``, or empty.

    Upstream keys the file by site, with an ``answers`` list whose items carry
    a numeric ``id`` that is the suffix of the task id. Anything that does not
    look like that is skipped rather than guessed at.
    """
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    refs: dict[str, list[dict[str, Any]]] = {}
    for site, block in raw.items():
        answers = block.get("answers") if isinstance(block, dict) else None
        if not isinstance(answers, list):
            continue
        for item in answers:
            if not isinstance(item, dict) or "id" not in item:
                continue
            key = f"{site}--{item['id']}"
            refs.setdefault(key, []).append(item)
    return refs


def _reference_text(entries: list[dict[str, Any]]) -> str:
    lines = []
    for item in entries:
        grade = str(item.get("type") or "reference")
        answer = str(item.get("ans") or "").strip()
        if answer:
            lines.append(f"[{grade}] {answer}")
    return "\n".join(lines)


@register
class WebVoyagerAdapter(AdapterBase):
    name = "webvoyager"
    upstream = "https://github.com/MinorJerry/WebVoyager"
    # Pinning lands with the shared _pins.yaml (issue #72, step 5).
    pinned_sha = None
    scoring_layers = (
        ScoringLayer.SUBMISSION_INTERCEPT,
        ScoringLayer.LLM_JUDGE_ONLY,
    )

    def load(self, path: Path) -> list[ClawBenchTask]:
        data_file = path if path.is_file() else path / DATA_FILE
        if not data_file.is_file():
            raise AdapterError(
                f"{self.name}: no {DATA_FILE.as_posix()} under {path} "
                "(expected a WebVoyager checkout, or a path to the .jsonl itself)"
            )
        root = data_file.parent.parent if data_file.parent.name == "data" else path
        references = _load_references(root / REFERENCE_FILE)
        references_present = bool(references)

        tasks: list[ClawBenchTask] = []
        with data_file.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as e:
                    raise AdapterError(
                        f"{self.name}: {data_file}:{line_no}: not JSON: {e}"
                    ) from None
                if not isinstance(raw, dict):
                    raise AdapterError(
                        f"{self.name}: {data_file}:{line_no}: expected an object"
                    )
                tasks.append(
                    self._convert(
                        raw,
                        references=references,
                        references_present=references_present,
                        where=f"{data_file.name}:{line_no}",
                    )
                )
        if not tasks:
            raise AdapterError(f"{self.name}: {data_file} holds no tasks")
        return tasks

    def _convert(
        self,
        raw: dict[str, Any],
        *,
        references: dict[str, list[dict[str, Any]]],
        references_present: bool,
        where: str,
    ) -> ClawBenchTask:
        source_id = str(raw.get("id") or "").strip()
        question = str(raw.get("ques") or "").strip()
        if not source_id or not question:
            raise AdapterError(
                f"{self.name}: {where}: every task needs a non-empty `id` and `ques`"
            )
        warnings: list[AdapterWarning] = []

        def warn(field_name: str, message: str, fallback: str | None = None) -> None:
            warnings.append(
                AdapterWarning(
                    source=self.name,
                    task_id=source_id,
                    field_name=field_name,
                    message=message,
                    fallback=fallback,
                    upstream_sha=self.pinned_sha,
                )
            )

        url = raw.get("web")
        if not isinstance(url, str) or not url.strip():
            warn("url", "task has no `web` start URL", "agent must find the site")
            url = None

        site = raw.get("web_name")
        category = site.strip() if isinstance(site, str) and site.strip() else None
        if category is None:
            warn("category", "task has no `web_name`", "uncategorised")

        judge_context: dict[str, Any] = {}
        entries = references.get(source_id, [])
        reference = _reference_text(entries)
        if reference:
            judge_context["reference_solution"] = reference
            judge_context["rubric"] = (
                "Judge the submitted answer against the reference answers. "
                "A [golden] reference is the exact expected answer; a [possible] "
                "reference is an acceptable alternative. The answer passes if it "
                "conveys the same facts as a golden or possible reference, "
                "allowing for wording and formatting differences."
            )
        elif references_present:
            warn(
                "judge_context",
                "no reference answer for this id",
                "judge on question alone",
            )
        else:
            warn(
                "judge_context",
                f"{REFERENCE_FILE.as_posix()} not found in checkout",
                "judge on question alone",
            )

        return ClawBenchTask(
            task_id=source_id.lower(),
            source=self.name,
            source_id=source_id,
            instruction=question + SUBMIT_FOOTER,
            url=url,
            category=category,
            time_limit=DEFAULT_TIME_LIMIT_MINUTES,
            eval_schema=dict(SUBMIT_EVAL_SCHEMA),
            scoring_layers=self.scoring_layers,
            judge_context=judge_context,
            metadata={
                "description": question,
                "sites_involved": [urlparse(url).netloc] if url else [],
                "source_task_id": source_id,
                "source_site": category,
            },
            warnings=tuple(warnings),
        )
