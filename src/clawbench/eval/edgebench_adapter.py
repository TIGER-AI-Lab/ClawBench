"""``clawbench-edgebench-adapt`` — export ClawBench V2 tasks as an EdgeBench/SForge benchmark.

Emits a SForge benchmark directory (``tasks/BENCHMARK.yaml`` + ``tasks/<id>.json``)
that packages each ClawBench task as a two-container SForge task under
**Mapping A** (structured_json score task, zero SForge source edits):

* the **Work** container runs the ClawBench browser agent + interceptor; the
  interceptor writes ``evidence/interception.json``; the agent calls
  ``sforge-submit`` once;
* the **Judge** container's ``eval_cmd`` is ``clawbench-edgebench-judge`` over the
  submitted ``evidence/`` → a ``structured_json`` block with ``score``/``valid``.

The short one-shot browser task is run with SForge's long-horizon machinery
disabled (``--max-submissions 1 --disable-auto-eval --disable-stop-hook``); see
``docs/edgebench.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from clawbench.eval.harbor_adapter import (
    DEFAULT_CASES_DIR,
    copy_extra_info,
    discover_cases,
)
from clawbench.runner.run_support.task import build_instruction, prepare_personal_info
from clawbench.utils.paths import SHARED_ROOT

# Default combined runtime image (browser + harness + harbor scripts + verifier).
DEFAULT_BASE_IMAGE = "clawbench-prorl-openclaw:latest"

# Fixed persona identity for the staged my-info bundle (static benchmark; no live
# inbox — email-signup tasks are out of scope for the EdgeBench packaging).
_PERSONA_EMAIL = "alex.green@example.com"
_PERSONA_PASSWORD = "clawbench-edgebench"  # noqa: S105 (placeholder, not a secret)


def sforge_task_id(task_id: str) -> str:
    """SForge requires lowercase_underscore ids: map every other char to '_'."""
    sid = re.sub(r"[^a-z0-9_]+", "_", task_id.lower()).strip("_")
    return re.sub(r"_+", "_", sid) or "task"


def benchmark_yaml(base_image: str) -> str:
    """The SForge BENCHMARK.yaml: benchmark name + the base-image registry."""
    doc = {
        "name": "clawbench",
        "base_images": {
            "browser": {
                "official_image": base_image,
                "extra_packages": ["git", "curl", "jq"],
            }
        },
    }
    return yaml.safe_dump(doc, sort_keys=False)


def edgebench_agent_query(task: dict[str, Any]) -> str:
    """The Work-container prompt: the ClawBench instruction + the submit protocol."""
    instruction = build_instruction(task)
    return (
        instruction + "\n\n---\n"
        "EdgeBench submission protocol:\n"
        "- Complete the task through the existing Chromium session (CDP on "
        "http://127.0.0.1:9223); do not launch a separate browser.\n"
        "- The ClawBench interceptor records the target request to "
        "`evidence/interception.json` as you act.\n"
        "- When the task is done, run `sforge-submit` ONCE to submit `evidence/` "
        "for grading. Your score is the best submission.\n"
        "---\n"
    )


def build_task_json(
    task_id: str,
    task: dict[str, Any],
    *,
    base_image: str,
    eval_timeout: int,
) -> dict[str, Any]:
    """Build the SForge task.json (Mapping A) for one ClawBench task."""
    sforge_id = sforge_task_id(task_id)
    raw_meta = task.get("metadata")
    metadata = raw_meta if isinstance(raw_meta, dict) else {}
    name = str(metadata.get("description") or task.get("instruction") or task_id)[:120]
    return {
        "task_id": sforge_id,
        "name": name,
        "base_image": "browser",
        "platform": "linux/amd64",
        "cwd": "/app",
        "submit_paths": ["evidence/"],
        "submit_exclude": ["tests/", "my-info/"],
        "internet": True,
        "game_mode": False,
        "work": {
            # The combined image already has the browser runtime + harness; setup
            # seeds the task and prepares the evidence dir.
            "setup_cmds": [
                "mkdir -p /app/evidence",
                "cp /specs/task.json /app/task.json",
                "cp /specs/eval-schema.json /app/eval-schema.json",
                # the runtime-server reads /eval-schema.json to arm the interceptor
                "cp /specs/eval-schema.json /eval-schema.json",
                # stage the personal-info bundle the instruction references
                "cp -r /specs/my-info /app/my-info",
            ],
            "specs_dir": "specs",
            "agent_query": edgebench_agent_query(task),
        },
        "judge": {
            # The judge re-scores the submitted evidence with the ClawBench verifier.
            # The judge image must provide the `clawbench-edgebench-judge` console
            # script — install the package here (a base image that already bundles
            # it can drop this line).
            "setup_cmds": [
                "pip install --quiet --no-cache-dir clawbench-eval",
                "cp /specs/task.json /judge/task.json",
            ],
            "specs_dir": "specs",
            "eval_cmd": (
                "clawbench-edgebench-judge --task-json /judge/task.json "
                "--evidence-dir /app/evidence"
            ),
            "eval_timeout": eval_timeout,
            "parser": "structured_json",
            "score_direction": "maximize",
            "selection": "score_first",
        },
    }


def write_benchmark(
    cases: list[tuple[Path, dict[str, Any]]],
    output_dir: Path,
    *,
    base_image: str,
    eval_timeout: int,
) -> list[Path]:
    """Write BENCHMARK.yaml + per-task JSON + per-task specs; return task-json paths."""
    tasks_dir = output_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (tasks_dir / "BENCHMARK.yaml").write_text(benchmark_yaml(base_image))

    written: list[Path] = []
    seen: dict[str, str] = {}
    for task_dir, task in cases:
        spec = build_task_json(
            task_dir.name, task, base_image=base_image, eval_timeout=eval_timeout
        )
        sid = spec["task_id"]
        if sid in seen:
            raise ValueError(
                f"sforge task_id collision: {task_dir.name!r} and {seen[sid]!r} "
                f"both sanitize to {sid!r}"
            )
        seen[sid] = task_dir.name
        # per-task specs (copied into both containers at build via specs_dir)
        specs = tasks_dir / sid / "specs"
        specs.mkdir(parents=True, exist_ok=True)
        (specs / "task.json").write_text(json.dumps(task, indent=2, ensure_ascii=False))
        (specs / "eval-schema.json").write_text(
            json.dumps(task["eval_schema"], indent=2, ensure_ascii=False)
        )
        _stage_my_info(task, task_dir, specs / "my-info")
        task_path = tasks_dir / f"{sid}.json"
        task_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
        written.append(task_path)
    return written


def _guard_extra_info(task: dict[str, Any], task_dir: Path) -> None:
    """Reject extra_info paths that are absolute or escape the task dir.

    harbor_adapter.copy_extra_info joins ``task_dir / item['path']`` with no
    containment check, so a crafted task could stage arbitrary host files into the
    shareable benchmark. Fail loud on any such path.
    """
    for item in task.get("extra_info") or []:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        rel = str(item["path"])
        if Path(rel).is_absolute():
            raise ValueError(f"extra_info path must be relative: {rel!r}")
        try:
            (task_dir / rel).resolve().relative_to(task_dir.resolve())
        except ValueError as e:
            raise ValueError(f"extra_info path escapes the task dir: {rel!r}") from e


def _stage_my_info(task: dict[str, Any], task_dir: Path, dest: Path) -> None:
    """Pre-generate the my-info bundle (persona + creds + resume) + extra_info.

    build_instruction() promises ./my-info/ contains these files, so we stage them
    at adapt time (SForge setup_cmds run at build with no runtime keys). A fixed
    placeholder persona email is used; email-signup tasks are out of scope.
    """
    _guard_extra_info(task, task_dir)
    tmp, _ = prepare_personal_info(
        SHARED_ROOT, _PERSONA_EMAIL, _PERSONA_PASSWORD, dest.parent
    )
    if dest.exists():
        shutil.rmtree(dest)
    tmp.rename(dest)
    copy_extra_info(task, task_dir, dest)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawbench-edgebench-adapt",
        description="Export ClawBench V2 tasks as an EdgeBench/SForge benchmark directory.",
    )
    p.add_argument(
        "--output-dir", type=Path, required=True, help="Benchmark output dir"
    )
    p.add_argument(
        "--task-ids", default="", help="Comma-separated task ids (default: all V2)"
    )
    p.add_argument(
        "--cases-dir", type=Path, default=None, help="V2 cases dir (default: bundled)"
    )
    p.add_argument(
        "--base-image", default=DEFAULT_BASE_IMAGE, help="SForge base official_image"
    )
    p.add_argument(
        "--eval-timeout", type=int, default=180, help="Judge eval_timeout (s)"
    )
    p.add_argument("--limit", type=int, default=None, help="Cap number of tasks")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases_dir = (args.cases_dir or DEFAULT_CASES_DIR).resolve()
    if not cases_dir.exists():
        print(f"ERROR: cases dir not found: {cases_dir}", file=sys.stderr)
        return 1
    requested = {t.strip() for t in args.task_ids.split(",") if t.strip()}
    cases = discover_cases(cases_dir, requested)
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        print("ERROR: no matching V2 tasks found", file=sys.stderr)
        return 1
    try:
        written = write_benchmark(
            cases,
            args.output_dir,
            base_image=args.base_image,
            eval_timeout=args.eval_timeout,
        )
    except (OSError, ValueError) as e:
        print(f"ERROR: failed to write benchmark: {e}", file=sys.stderr)
        return 1
    print(f"Wrote {len(written)} EdgeBench task(s) to {args.output_dir / 'tasks'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
