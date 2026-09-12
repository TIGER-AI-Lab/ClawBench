"""The shared task type every source adapter converts into.

``ClawBenchTask`` is a superset of what ``test-cases/task.schema.json``
encodes, plus the provenance fields an imported task needs: which source it
came from, that source's own identifier for it, and which scoring layers the
source can actually support. Adapters build these; the runner consumes
``to_task_json()``.

Validation is hand-rolled rather than delegated to Pydantic because the rest
of the package validates its registries the same way (see
``runner/run_support/harness_registry.py``) and ClawBench has no Pydantic
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Metaclass/platform stamped on the `metadata` block of an imported task so a
# leaderboard can partition rows by origin without reparsing the source repo.
IMPORTED_METACLASS = "imported"


class ScoringLayer(str, Enum):
    """A scoring mechanism an adapter declares its tasks can be judged by.

    An adapter MUST declare the layers it supports. Layers ClawBench runs but
    the source cannot support score ``null`` in the recording rather than 0,
    so leaderboard aggregation never conflates "the agent failed" with "this
    task was never scored on that axis".
    """

    SUBMISSION_INTERCEPT = "submission_intercept"
    END_STATE_DOM_MATCH = "end_state_dom_match"
    STEP_TRACE_REPLAY = "step_trace_replay"
    GOAL_PREDICATE = "goal_predicate"
    LLM_JUDGE_ONLY = "llm_judge_only"


@dataclass(frozen=True)
class AdapterWarning:
    """One field-mapping gap, raised at load time rather than at run time.

    ``upstream_sha`` records the pinned revision the adapter was written
    against, so a warning tells a reader both what is missing now and which
    upstream state it was missing from.
    """

    source: str
    message: str
    task_id: str | None = None
    field_name: str | None = None
    upstream_sha: str | None = None
    fallback: str | None = None

    def __str__(self) -> str:
        parts = [f"[{self.source}"]
        if self.task_id:
            parts.append(f"/{self.task_id}")
        parts.append("] ")
        head = "".join(parts)
        detail = self.message
        if self.field_name:
            detail = f"{self.field_name}: {detail}"
        if self.fallback:
            detail = f"{detail} (using {self.fallback})"
        if self.upstream_sha:
            detail = f"{detail} [upstream {self.upstream_sha}]"
        return head + detail


@dataclass(frozen=True)
class ExtraInfo:
    """One entry of a task's ``extra_info`` list."""

    description: str
    path: str | None = None

    def to_json(self) -> dict[str, str]:
        entry: dict[str, str] = {}
        if self.path:
            entry["path"] = self.path
        entry["description"] = self.description
        return entry


@dataclass(frozen=True)
class ClawBenchTask:
    """A task in ClawBench's own terms, whatever benchmark it came from.

    ``time_limit`` is in **minutes**, matching ``task.json`` and the container
    watchdog — not the seconds most upstream schemas use. Adapters convert.
    """

    task_id: str
    source: str
    instruction: str
    time_limit: float
    eval_schema: dict[str, Any] | None = None
    url: str | None = None
    category: str | None = None
    source_id: str | None = None
    scoring_layers: tuple[ScoringLayer, ...] = ()
    extra_info: tuple[ExtraInfo, ...] = ()
    judge_context: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[AdapterWarning, ...] = ()

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        if not self.source.strip():
            raise ValueError(f"{self.task_id}: source must be a non-empty string")
        if not self.instruction.strip():
            raise ValueError(f"{self.task_id}: instruction must be a non-empty string")
        if isinstance(self.time_limit, bool) or not isinstance(
            self.time_limit, (int, float)
        ):
            raise ValueError(f"{self.task_id}: time_limit must be a number")
        if self.time_limit <= 0:
            raise ValueError(f"{self.task_id}: time_limit must be greater than 0")
        if self.eval_schema is not None:
            for key in ("url_pattern", "method"):
                if not isinstance(self.eval_schema.get(key), str):
                    raise ValueError(
                        f"{self.task_id}: eval_schema.{key} must be a string"
                    )
        for layer in self.scoring_layers:
            if not isinstance(layer, ScoringLayer):
                raise ValueError(
                    f"{self.task_id}: scoring_layers must contain ScoringLayer values"
                )
        if ScoringLayer.SUBMISSION_INTERCEPT in self.scoring_layers and (
            self.eval_schema is None
        ):
            raise ValueError(
                f"{self.task_id}: submission_intercept scoring requires an eval_schema"
            )

    def supports(self, layer: ScoringLayer) -> bool:
        return layer in self.scoring_layers

    def to_task_json(self) -> dict[str, Any]:
        """Render this task in ``test-cases/task.schema.json`` shape.

        ``eval_schema`` is required by the schema, so a task whose source has
        no interception contract cannot be written out as a native task.
        Callers should check :meth:`supports` first.
        """
        if self.eval_schema is None:
            raise ValueError(
                f"{self.task_id}: cannot render task.json without an eval_schema "
                "(source does not support submission_intercept)"
            )
        task: dict[str, Any] = {
            "metadata": {
                "task_id": self.task_id,
                "metaclass": self.metadata.get("metaclass", IMPORTED_METACLASS),
                "class": self.category or self.source,
                "description": self.metadata.get("description", self.task_id),
                "sites_involved": list(self.metadata.get("sites_involved", [])),
                "platform": self.source,
                "source": self.source,
                "source_id": self.source_id or self.task_id,
            },
            "instruction": self.instruction,
            "eval_schema": dict(self.eval_schema),
            "time_limit": float(self.time_limit),
        }
        if self.extra_info:
            task["extra_info"] = [info.to_json() for info in self.extra_info]
        if self.judge_context:
            task["judge_context"] = dict(self.judge_context)
        return task
