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
import sys
from pathlib import Path
from typing import Any

import yaml

from clawbench.eval.harbor_adapter import (
    DEFAULT_CASES_DIR,
    discover_cases,
    sanitize_task_name,
)
from clawbench.runner.run_support.task import build_instruction

# Default combined runtime image (browser + harness + harbor scripts + verifier).
DEFAULT_BASE_IMAGE = "clawbench-prorl-openclaw:latest"


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
    sforge_id = sanitize_task_name(task_id).replace("-", "_").lower()
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
            ],
            "specs_dir": "specs",
            "agent_query": edgebench_agent_query(task),
        },
        "judge": {
            # The judge re-scores the submitted evidence with the ClawBench verifier.
            "setup_cmds": [
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
    seen: set[str] = set()
    for task_dir, task in cases:
        spec = build_task_json(
            task_dir.name, task, base_image=base_image, eval_timeout=eval_timeout
        )
        sid = spec["task_id"]
        if sid in seen:
            continue
        seen.add(sid)
        # per-task specs (copied into both containers at build via specs_dir)
        specs = tasks_dir / sid / "specs"
        specs.mkdir(parents=True, exist_ok=True)
        (specs / "task.json").write_text(json.dumps(task, indent=2, ensure_ascii=False))
        (specs / "eval-schema.json").write_text(
            json.dumps(task["eval_schema"], indent=2, ensure_ascii=False)
        )
        task_path = tasks_dir / f"{sid}.json"
        task_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
        written.append(task_path)
    return written


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
    written = write_benchmark(
        cases,
        args.output_dir,
        base_image=args.base_image,
        eval_timeout=args.eval_timeout,
    )
    print(f"Wrote {len(written)} EdgeBench task(s) to {args.output_dir / 'tasks'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
