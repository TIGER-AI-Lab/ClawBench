"""Adapter base class and the source registry.

An adapter converts one external benchmark's task definitions into
:class:`~clawbench.adapters.schema.ClawBenchTask` values. It is import-only:
nothing here writes back to an upstream format.

Each adapter subclasses :class:`AdapterBase`, declares which scoring layers it
can honour, pins the upstream revision it was written against, and documents
its field mapping in its module docstring. Registration is by decorator:

    @register
    class MyAdapter(AdapterBase):
        name = "my-benchmark"
        ...
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from clawbench.adapters.schema import ClawBenchTask, ScoringLayer


class AdapterError(RuntimeError):
    """A source could not be loaded at all."""


@dataclass(frozen=True)
class SourceStatus:
    """What ``clawbench-sources list`` prints for one registered adapter."""

    name: str
    upstream: str | None
    pinned_sha: str | None
    scoring_layers: tuple[ScoringLayer, ...]
    cache_dir: Path
    cached: bool
    bundled: bool


class AdapterBase(ABC):
    """Base class for every task-source adapter."""

    #: Registry key, also the value accepted by ``--source``.
    name: str = ""
    #: Upstream repository this adapter reads, or ``None`` when the tasks ship
    #: with ClawBench itself.
    upstream: str | None = None
    #: Upstream commit/tag the field mapping was written against. Pinning keeps
    #: an upstream rename from silently changing what a run measures.
    pinned_sha: str | None = None
    #: Scoring layers this source's tasks can actually be judged by. Layers not
    #: listed here score ``null``, never 0.
    scoring_layers: tuple[ScoringLayer, ...] = ()

    @property
    def bundled(self) -> bool:
        """True when the source needs no external checkout."""
        return self.upstream is None

    @abstractmethod
    def load(self, path: Path) -> list[ClawBenchTask]:
        """Convert every task under ``path`` into ClawBench tasks.

        Implementations raise :class:`AdapterError` when ``path`` is not a
        checkout of this source, and attach an
        :class:`~clawbench.adapters.schema.AdapterWarning` to a task for each
        field they could not map, rather than dropping the task silently.
        """

    def default_path(self) -> Path:
        """Where this source is expected to live when ``--source`` gets no path."""
        return source_cache_dir() / self.name

    def status(self, path: Path | None = None) -> SourceStatus:
        resolved = path or self.default_path()
        return SourceStatus(
            name=self.name,
            upstream=self.upstream,
            pinned_sha=self.pinned_sha,
            scoring_layers=self.scoring_layers,
            cache_dir=resolved,
            cached=resolved.is_dir(),
            bundled=self.bundled,
        )


_REGISTRY: dict[str, AdapterBase] = {}


def register(adapter_cls: type[AdapterBase]) -> type[AdapterBase]:
    """Register an adapter class under its ``name``."""
    name = adapter_cls.name
    if not name:
        raise ValueError(f"{adapter_cls.__name__} must define a non-empty name")
    if name in _REGISTRY:
        raise ValueError(f"duplicate adapter name: {name}")
    _REGISTRY[name] = adapter_cls()
    return adapter_cls


def registered_sources() -> tuple[str, ...]:
    """Every registered source name, in stable alphabetical order."""
    return tuple(sorted(_REGISTRY))


def get_adapter(name: str) -> AdapterBase:
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(registered_sources()) or "(none)"
        raise AdapterError(
            f"unknown task source {name!r}; registered sources: {known}"
        ) from None


def source_cache_dir() -> Path:
    """Root for lazily fetched source checkouts.

    Honours ``CLAWBENCH_SOURCES_DIR``, then ``XDG_CACHE_HOME``, then
    ``~/.cache``, so a shared machine can point several workspaces at one
    checkout without re-cloning.
    """
    if raw := os.environ.get("CLAWBENCH_SOURCES_DIR"):
        return Path(raw).expanduser()
    if raw := os.environ.get("XDG_CACHE_HOME"):
        return Path(raw).expanduser() / "clawbench" / "sources"
    return Path.home() / ".cache" / "clawbench" / "sources"


def parse_source_spec(spec: str) -> tuple[str, Path | None]:
    """Split ``--source`` into a registered name and an optional explicit path.

    ``"claw-eval"`` resolves to the adapter's default checkout location;
    ``"claw-eval:/path/to/repo"`` pins it to an explicit clone. Windows drive
    letters are not mistaken for the separator.
    """
    name, sep, raw_path = spec.partition(":")
    if not sep or len(name) <= 1:
        return spec, None
    return name, Path(raw_path).expanduser()


def offline() -> bool:
    """True when ``CLAWBENCH_OFFLINE`` forbids network fetches."""
    return os.environ.get("CLAWBENCH_OFFLINE", "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
    )
