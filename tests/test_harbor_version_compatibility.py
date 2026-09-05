"""Does the adapter's output still load in the Harbor version the docs pin?

Skipped unless Harbor is installed -- it is not a ClawBench dependency. The
point of the test is to make a version bump checkable instead of assumed:

    uv run --with harbor==<new-version> pytest tests/test_harbor_version_compatibility.py

The docs pinned harbor==0.15.0 for six releases past upstream (#294). Nothing
in the repo could tell you whether that mattered, because nothing ever loaded
a generated task with Harbor's own loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clawbench.eval import harbor_adapter

harbor_task = pytest.importorskip(
    "harbor.models.task.task",
    reason="Harbor is not installed; run with `uv run --with harbor==<version>`",
)

# The version docs/harbor.md pins and claims to have verified. A mismatch is
# not a failure -- the point is to make the tested version visible in output.
DOCUMENTED_HARBOR_VERSION = "0.22.0"


@pytest.fixture(scope="module")
def generated_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Convert the real V2 corpus, not a synthetic task.

    A hand-built fixture would only prove the fixture loads. What has to hold
    is that the corpus we tell people to convert produces a dataset Harbor
    accepts.
    """
    out = tmp_path_factory.mktemp("harbor-dataset") / "clawbench-v2"
    rc = harbor_adapter.main(["--output-dir", str(out), "--overwrite"])
    assert rc == 0
    return out


def test_installed_harbor_version_is_reported(record_property) -> None:
    from importlib.metadata import version

    installed = version("harbor")
    record_property("harbor_version", installed)
    if installed != DOCUMENTED_HARBOR_VERSION:
        pytest.skip(
            f"harbor {installed} installed, docs pin {DOCUMENTED_HARBOR_VERSION}; "
            "the load test below still runs"
        )


def test_every_generated_task_loads_with_harbors_own_loader(
    generated_dataset: Path,
) -> None:
    task_dirs = sorted(d for d in generated_dataset.iterdir() if d.is_dir())
    assert task_dirs

    failures: list[tuple[str, str]] = []
    for task_dir in task_dirs:
        if not harbor_task.Task.is_valid_dir(task_dir):
            failures.append((task_dir.name, "Harbor does not recognise the directory"))
            continue
        try:
            harbor_task.Task(task_dir)
        except Exception as exc:  # noqa: BLE001 - report whatever Harbor raises
            failures.append((task_dir.name, f"{type(exc).__name__}: {exc}"))

    assert not failures, "\n".join(f"{name}: {why}" for name, why in failures)
