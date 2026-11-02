"""Harness Dockerfile selection and CI summary generation for check-harness-build."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
import json
from pathlib import Path

DEFAULT_RUNTIME_ROOT = "src/clawbench/runtime"
DEFAULT_HARNESS_ROOT = f"{DEFAULT_RUNTIME_ROOT}/harnesses"
DEFAULT_BASE_DOCKERFILE = f"{DEFAULT_HARNESS_ROOT}/base/Dockerfile.base"

# Shared directories copied into or relied upon by the base harness image.
# Note: the legacy "extension-server/" directory was renamed to "runtime-server/".
SHARED_BASE_PREFIXES: tuple[str, ...] = (
    f"{DEFAULT_HARNESS_ROOT}/base/",
    f"{DEFAULT_RUNTIME_ROOT}/runtime-server/",
    f"{DEFAULT_RUNTIME_ROOT}/chrome-extension/",
    f"{DEFAULT_RUNTIME_ROOT}/shared/",
)


@dataclass(frozen=True)
class HarnessBuildPlan:
    build_all: bool
    base_dockerfile: str
    selected_dockerfiles: tuple[str, ...]

    @property
    def selection_mode(self) -> str:
        return "all" if self.build_all else "changed"

    @property
    def count(self) -> int:
        return len(self.selected_dockerfiles)

    def matrix_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "include": [
                {
                    "harness": Path(path).parent.name,
                    "dockerfile": path,
                    "image": f"clawbench-{Path(path).parent.name}",
                }
                for path in self.selected_dockerfiles
            ]
        }

    def matrix_json(self) -> str:
        return json.dumps(self.matrix_dict(), separators=(",", ":"))


def _normalize_rel_path(path: str | Path) -> str:
    return Path(path).as_posix().lstrip("./")


def discover_harness_dockerfiles(
    repo_root: Path = Path("."),
    *,
    harness_root: str = DEFAULT_HARNESS_ROOT,
    base_dockerfile: str = DEFAULT_BASE_DOCKERFILE,
) -> tuple[str, ...]:
    """Discover all downstream harness Dockerfiles under ``harness_root``."""
    root = repo_root / harness_root
    norm_base = _normalize_rel_path(base_dockerfile)
    found: list[str] = []
    if not root.is_dir():
        return ()
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        for candidate in sorted(subdir.glob("Dockerfile*")):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(repo_root).as_posix()
            if rel != norm_base:
                found.append(rel)
    return tuple(sorted(found))


def select_harness_build_plan(
    changed_runtime_files: Sequence[str],
    *,
    event_name: str = "pull_request",
    repo_root: Path = Path("."),
    runtime_root: str = DEFAULT_RUNTIME_ROOT,
    harness_root: str = DEFAULT_HARNESS_ROOT,
    base_dockerfile: str = DEFAULT_BASE_DOCKERFILE,
    all_harness_dockerfiles: Sequence[str] | None = None,
) -> HarnessBuildPlan:
    """Compute which downstream harness Dockerfiles must be built for a change set."""
    norm_runtime_root = _normalize_rel_path(runtime_root).rstrip("/")
    norm_harness_root = _normalize_rel_path(harness_root).rstrip("/")
    norm_base_dockerfile = _normalize_rel_path(base_dockerfile)

    available = (
        tuple(sorted(_normalize_rel_path(p) for p in all_harness_dockerfiles))
        if all_harness_dockerfiles is not None
        else discover_harness_dockerfiles(
            repo_root,
            harness_root=norm_harness_root,
            base_dockerfile=norm_base_dockerfile,
        )
    )
    available_set = set(available)

    shared_prefixes = (
        f"{norm_harness_root}/base/",
        f"{norm_runtime_root}/runtime-server/",
        f"{norm_runtime_root}/chrome-extension/",
        f"{norm_runtime_root}/shared/",
    )

    normalized_changes = [
        _normalize_rel_path(p) for p in changed_runtime_files if str(p).strip()
    ]

    build_all = event_name == "workflow_dispatch" or len(normalized_changes) == 0
    changed_dockerfiles: set[str] = set()

    if not build_all:
        harness_prefix = f"{norm_harness_root}/"
        for path in normalized_changes:
            if any(path.startswith(prefix) for prefix in shared_prefixes):
                build_all = True
                break
            if path.startswith(harness_prefix):
                remainder = path[len(harness_prefix) :]
                harness = remainder.split("/", 1)[0]
                if not harness or harness == "base":
                    continue
                dockerfile = f"{norm_harness_root}/{harness}/Dockerfile.{harness}"
                if dockerfile in available_set or (repo_root / dockerfile).is_file():
                    changed_dockerfiles.add(dockerfile)

    if build_all:
        selected = available
    else:
        selected = tuple(
            sorted(df for df in changed_dockerfiles if df != norm_base_dockerfile)
        )

    return HarnessBuildPlan(
        build_all=build_all,
        base_dockerfile=norm_base_dockerfile,
        selected_dockerfiles=selected,
    )


def format_harness_build_summary(event_name: str, plan: HarnessBuildPlan) -> str:
    """Render the GitHub Actions step summary markdown for a harness build plan."""
    lines = [
        "## Harness build plan",
        "",
        f"- Event: `{event_name}`",
        f"- Selection mode: `{plan.selection_mode}`",
        "- Base image: `clawbench-base`, `clawbench-base:amd64`",
        f"- Harness images: `{plan.count}`",
        "",
        "| Image | Dockerfile |",
        "| --- | --- |",
        f"| `clawbench-base`, `clawbench-base:amd64` | `{plan.base_dockerfile}` |",
    ]
    for dockerfile in plan.selected_dockerfiles:
        harness = Path(dockerfile).parent.name
        lines.append(f"| `clawbench-{harness}` | `{dockerfile}` |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select downstream harness Dockerfiles for CI."
    )
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--github-output", type=Path, default=None)
    parser.add_argument("--github-step-summary", type=Path, default=None)
    parser.add_argument("changed_files", nargs="*")
    args = parser.parse_args(list(argv) if argv is not None else None)

    plan = select_harness_build_plan(
        args.changed_files,
        event_name=args.event_name,
        repo_root=args.repo_root,
    )

    if args.github_output is not None:
        with args.github_output.open("a", encoding="utf-8") as fh:
            fh.write(f"matrix={plan.matrix_json()}\n")
            fh.write(f"count={plan.count}\n")

    print(f"Selected {plan.count} harness Dockerfile(s):")
    for dockerfile in plan.selected_dockerfiles:
        print(f"  {dockerfile}")
    print(
        f"::notice title=Harness build plan::Selected {plan.count} harness Dockerfile(s)"
    )

    if args.github_step_summary is not None:
        summary = format_harness_build_summary(args.event_name, plan)
        with args.github_step_summary.open("a", encoding="utf-8") as fh:
            fh.write(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
