"""Typed models for the Polar (ProRL-Agent-Server) ``TaskRequest`` payload.

Field names and nesting mirror ``src/polar/rollout/models.py`` and
``src/polar/{agent,runtime,trajectory}/models.py`` from
NVIDIA-NeMo/ProRL-Agent-Server (``stable`` branch). ``to_payload()`` emits the
exact JSON accepted by ``POST /rollout/task/submit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clean(d: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is ``None`` so the payload stays minimal."""
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class PrepareAction:
    """One ordered step that seeds a session's runtime before the harness runs.

    Either an upload (``upload_file`` / ``upload_dir`` with ``source``/``target``)
    or an in-container ``exec`` (``command`` with optional ``cwd``/``env``).
    """

    type: str
    source: str | None = None
    target: str | None = None
    command: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None

    def __post_init__(self) -> None:
        valid = {"upload_file", "upload_dir", "exec"}
        if self.type not in valid:
            raise ValueError(f"PrepareAction.type must be one of {sorted(valid)}")
        if self.type in {"upload_file", "upload_dir"}:
            if not self.source or not self.target:
                raise ValueError(f"{self.type} requires source and target")
        elif not self.command:
            raise ValueError("exec requires command")

    def to_payload(self) -> dict[str, Any]:
        return _clean(
            {
                "type": self.type,
                "source": self.source,
                "target": self.target,
                "command": self.command,
                "cwd": self.cwd,
                "env": self.env,
            }
        )


@dataclass
class RuntimeSpec:
    image: str
    backend: str = "docker"
    workdir: str = "/app"
    network: str = "host"
    allow_internet: bool = True
    gpus: int = 0
    prepare: list[PrepareAction] = field(default_factory=list)
    eval_prepare: list[PrepareAction] = field(default_factory=list)
    env: dict[str, str] | None = None

    def to_payload(self) -> dict[str, Any]:
        return _clean(
            {
                "backend": self.backend,
                "image": self.image,
                "workdir": self.workdir,
                "network": self.network,
                "allow_internet": self.allow_internet,
                "gpus": self.gpus,
                "prepare": [p.to_payload() for p in self.prepare],
                "eval_prepare": [p.to_payload() for p in self.eval_prepare],
                "env": self.env,
            }
        )


@dataclass
class AgentSpec:
    """Polar agent/harness spec.

    Supply EITHER ``harness="shell"`` with ``custom_shell`` (the escape hatch,
    no Polar code) OR ``import_path="pkg.mod:MyHarness"``. ClawBench uses the
    shell harness so the browser episode's LLM calls traverse the gateway proxy.
    """

    model_name: str
    harness: str | None = "shell"
    custom_shell: dict[str, Any] | None = None
    import_path: str | None = None
    settings: dict[str, Any] | None = None
    env: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if bool(self.harness) == bool(self.import_path):
            raise ValueError("provide exactly one of harness or import_path")
        if self.harness == "shell" and not self.custom_shell:
            raise ValueError("shell harness requires custom_shell")
        if self.custom_shell is not None:
            if self.harness != "shell":
                raise ValueError("custom_shell is only valid with harness='shell'")
            if not self.custom_shell.get("command"):
                raise ValueError("custom_shell requires a 'command'")

    def to_payload(self) -> dict[str, Any]:
        return _clean(
            {
                "harness": self.harness,
                "custom_shell": self.custom_shell,
                "import_path": self.import_path,
                "model_name": self.model_name,
                "settings": self.settings,
                "env": self.env,
            }
        )


@dataclass
class BuilderSpec:
    """Trajectory builder. ``prefix_merging`` is recommended for multi-turn agents."""

    strategy: str = "prefix_merging"

    def to_payload(self) -> dict[str, Any]:
        return {"strategy": self.strategy}


@dataclass
class EvaluatorSpec:
    """Reward evaluator. ``harbor`` runs ``tests/test.sh`` and reads reward.json."""

    strategy: str = "harbor"
    config: dict[str, Any] = field(default_factory=dict)
    refresh_runtime: bool = False
    env: dict[str, str] | None = None

    def to_payload(self) -> dict[str, Any]:
        return _clean(
            {
                "strategy": self.strategy,
                "config": self.config,
                "refresh_runtime": self.refresh_runtime,
                "env": self.env,
            }
        )


@dataclass
class TaskRequest:
    task_id: str
    instruction: str
    runtime: RuntimeSpec
    agent: AgentSpec
    evaluator: EvaluatorSpec
    builder: BuilderSpec = field(default_factory=BuilderSpec)
    num_samples: int = 8
    timeout_seconds: int = 900
    callback_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.num_samples < 1:
            raise ValueError("num_samples must be >= 1")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

    def to_payload(self) -> dict[str, Any]:
        return _clean(
            {
                "task_id": self.task_id,
                "instruction": self.instruction,
                "num_samples": self.num_samples,
                "timeout_seconds": self.timeout_seconds,
                "runtime": self.runtime.to_payload(),
                "agent": self.agent.to_payload(),
                "builder": self.builder.to_payload(),
                "evaluator": self.evaluator.to_payload(),
                "callback_url": self.callback_url,
                "metadata": self.metadata,
            }
        )
