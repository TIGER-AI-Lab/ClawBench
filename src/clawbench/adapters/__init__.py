"""Task-source adapters: run other benchmarks' tasks under ClawBench.

Every adapter converts one external benchmark's task definitions into
:class:`~clawbench.adapters.schema.ClawBenchTask`, so a research team can reuse
ClawBench's submission interception, five-layer recording, and judge pipeline
without hand-converting task files or forking the upstream repo.

Adapters are import-only and pin the upstream revision they were written
against. Fields with no 1:1 mapping surface as
:class:`~clawbench.adapters.schema.AdapterWarning` at load time; scoring layers
a source cannot support score ``null`` rather than 0, so "not scored" is never
mistaken for "failed".

``clawbench-sources`` lists what is registered. See ``docs/task-sources.md``.
"""

from clawbench.adapters._base import (
    AdapterBase,
    AdapterError,
    SourceStatus,
    get_adapter,
    offline,
    parse_source_spec,
    register,
    registered_sources,
    source_cache_dir,
)
from clawbench.adapters.schema import (
    AdapterWarning,
    ClawBenchTask,
    ExtraInfo,
    ScoringLayer,
)

# Importing an adapter module is what registers it.
from . import native, webvoyager  # noqa: F401  isort:skip

__all__ = [
    "AdapterBase",
    "AdapterError",
    "AdapterWarning",
    "ClawBenchTask",
    "ExtraInfo",
    "ScoringLayer",
    "SourceStatus",
    "get_adapter",
    "offline",
    "parse_source_spec",
    "register",
    "registered_sources",
    "source_cache_dir",
]
