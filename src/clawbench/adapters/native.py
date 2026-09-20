"""Identity loader for ClawBench's own ``task.json`` corpora.

Field mapping (`test-cases/<suite>/<task-dir>/task.json` -> ``ClawBenchTask``):

| Field             | Source                                          |
|-------------------|-------------------------------------------------|
| ``task_id``       | the task directory name                         |
| ``instruction``   | ``instruction``                                 |
| ``time_limit``    | ``time_limit`` (already minutes)                |
| ``eval_schema``   | ``eval_schema``                                 |
| ``category``      | ``metadata.class``                              |
| ``source_id``     | ``metadata.task_id``, else the directory name   |
| ``extra_info``    | ``extra_info``                                  |
| ``judge_context`` | ``judge_context``                               |
| ``metadata``      | ``metadata``                                    |

Nothing is lost in this direction, so this adapter emits no warnings. It
exists so that bundled tasks and imported tasks reach the runner through one
code path — and so the registry has a reference implementation.

Validation deliberately lives in ``ClawBenchTask.__post_init__`` rather than
reusing ``runner.run_support.task.validate_task_data``: the two check the same
three invariants, and importing the runner would pull the PDF and container
helpers into a plain task listing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawbench.adapters._base import AdapterBase, AdapterError, register
from clawbench.adapters.schema import (
    ClawBenchTask,
    ExtraInfo,
    ScoringLayer,
)
from clawbench.utils.paths import asset_path


def _extra_info(raw: Any) -> tuple[ExtraInfo, ...]:
    if not isinstance(raw, list):
        return ()
    entries: list[ExtraInfo] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            entries.append(ExtraInfo(description=item.strip()))
        elif isinstance(item, dict):
            description = item.get("description")
            if not isinstance(description, str) or not description.strip():
                continue
            path = item.get("path")
            entries.append(
                ExtraInfo(
                    description=description.strip(),
                    path=path if isinstance(path, str) and path else None,
                )
            )
    return tuple(entries)


@register
class NativeAdapter(AdapterBase):
    name = "clawbench-native"
    upstream = None
    scoring_layers = (
        ScoringLayer.SUBMISSION_INTERCEPT,
        ScoringLayer.END_STATE_DOM_MATCH,
        ScoringLayer.LLM_JUDGE_ONLY,
    )

    def default_path(self) -> Path:
        """The bundled corpus root, which holds one directory per suite."""
        return asset_path("test-cases")

    def load(self, path: Path) -> list[ClawBenchTask]:
        if not path.is_dir():
            raise AdapterError(f"{self.name}: not a directory: {path}")
        # A suite directory holds tasks directly; the corpus root holds suites.
        task_files = sorted(path.glob("*/task.json")) or sorted(
            path.glob("*/*/task.json")
        )
        if not task_files:
            raise AdapterError(f"{self.name}: no <task>/task.json files under {path}")
        return [self._load_one(task_file) for task_file in task_files]

    def _load_one(self, task_file: Path) -> ClawBenchTask:
        try:
            raw = json.loads(task_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise AdapterError(f"{self.name}: cannot read {task_file}: {e}") from None
        if not isinstance(raw, dict):
            raise AdapterError(f"{self.name}: {task_file} must contain a JSON object")

        metadata = raw.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        judge_context = raw.get("judge_context")
        judge_context = judge_context if isinstance(judge_context, dict) else {}
        eval_schema = raw.get("eval_schema")
        source_id = metadata.get("task_id")

        try:
            return ClawBenchTask(
                task_id=task_file.parent.name,
                source=self.name,
                instruction=raw.get("instruction") or "",
                time_limit=raw.get("time_limit"),  # pyright: ignore[reportArgumentType]
                eval_schema=eval_schema if isinstance(eval_schema, dict) else None,
                category=(
                    metadata.get("class")
                    if isinstance(metadata.get("class"), str)
                    else None
                ),
                source_id=str(source_id) if source_id is not None else None,
                scoring_layers=self.scoring_layers,
                extra_info=_extra_info(raw.get("extra_info")),
                judge_context=judge_context,
                metadata=metadata,
            )
        except ValueError as e:
            raise AdapterError(f"{self.name}: {task_file}: {e}") from None
