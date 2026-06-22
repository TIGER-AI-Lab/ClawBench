"""Convert ClawBench V2 tasks into Harbor-compatible task directories."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.task import build_instruction, validate_task_data
from clawbench.utils.paths import RUNTIME_ROOT, asset_path

DEFAULT_CASES_DIR = asset_path("test-cases", "v2")
STEP_NAME = "run"


def sanitize_task_name(raw: str) -> str:
    name = raw.strip().lower()
    name = re.sub(r"[^a-z0-9._-]+", "-", name)
    name = re.sub(r"-+", "-", name).strip(".-_")
    if not name or not re.match(r"^[a-z0-9]", name):
        name = f"task-{name}"
    return name


def task_id_matches(task: dict[str, Any], task_dir: Path, requested: set[str]) -> bool:
    if not requested:
        return True
    raw_metadata = task.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    candidates = {
        task_dir.name,
        sanitize_task_name(task_dir.name),
    }
    if metadata.get("task_id") is not None:
        candidates.add(str(metadata["task_id"]))
        candidates.add(f"v2-{metadata['task_id']}")
    return bool(candidates & requested)


def discover_cases(
    cases_dir: Path, task_ids: set[str] | None = None
) -> list[tuple[Path, dict[str, Any]]]:
    requested = task_ids or set()
    cases: list[tuple[Path, dict[str, Any]]] = []
    for task_file in sorted(cases_dir.glob("*/task.json")):
        task_dir = task_file.parent
        try:
            task = validate_task_data(json.loads(task_file.read_text()), task_file)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid task data in {task_file}: {exc}") from exc
        if task_id_matches(task, task_dir, requested):
            cases.append((task_dir, task))
    return cases


def unique_output_name(task_dir: Path, seen: set[str]) -> str:
    base = sanitize_task_name(task_dir.name)
    name = base
    idx = 2
    while name in seen:
        name = f"{base}-{idx}"
        idx += 1
    seen.add(name)
    return name


def chmod_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def copytree_filtered(src: Path, dst: Path) -> None:
    def ignore(_dir: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name in {".venv", "__pycache__"}
            or name.endswith(".pyc")
            or name == ".DS_Store"
        }

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore)


def copy_environment(env_dir: Path) -> None:
    env_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RUNTIME_ROOT / "harbor" / "Dockerfile", env_dir / "Dockerfile")
    copytree_filtered(RUNTIME_ROOT / "runtime-server", env_dir / "runtime-server")
    copytree_filtered(RUNTIME_ROOT / "chrome-extension", env_dir / "chrome-extension")
    copytree_filtered(RUNTIME_ROOT / "shared", env_dir / "shared")
    copytree_filtered(RUNTIME_ROOT / "harbor", env_dir / "harbor")
    (env_dir / "harbor" / "Dockerfile").unlink(missing_ok=True)
    shutil.copy2(
        Path(__file__).resolve().parents[1]
        / "runner"
        / "run_support"
        / "resume_template.json",
        env_dir / "harbor" / "resume_template.json",
    )
    for script in env_dir.glob("harbor/*"):
        if script.suffix in {".sh", ".py"}:
            chmod_executable(script)


def harbor_instruction(task: dict[str, Any]) -> str:
    instruction = build_instruction(task)
    return (
        instruction + "\n\n---\n"
        "Harbor browser runtime:\n"
        "- Use the existing Chromium session exposed by Chrome DevTools Protocol.\n"
        "- CDP endpoint: http://127.0.0.1:9223\n"
        "- CDP environment variables are also set for the agent process: "
        "CLAWBENCH_CDP_URL, BROWSER_CDP_URL, CDP_URL, CHROME_CDP_URL, and PLAYWRIGHT_CDP_URL.\n"
        "- noVNC viewer, if needed: http://127.0.0.1:6080/vnc.html\n"
        "- Do not launch a separate browser. Complete the task through the existing browser session.\n"
        "---\n"
    )


def task_toml(
    *,
    package_name: str,
    description: str,
    dataset_name: str,
    timeout_sec: int,
    task_dir_name: str,
) -> str:
    escaped_description = json.dumps(description)
    escaped_dataset = json.dumps(dataset_name)
    escaped_source = json.dumps(task_dir_name)
    escaped_package = json.dumps(package_name)
    return f"""schema_version = "1.3"
source = "clawbench-v2"
artifacts = ["/data"]

[task]
name = {escaped_package}
description = {escaped_description}
keywords = ["clawbench", "v2", "web-agent", "browser"]

[metadata]
dataset = {escaped_dataset}
source_task = {escaped_source}

[environment]
build_timeout_sec = 1200.0
network_mode = "public"
workdir = "/app"

[environment.env]
PURELY_MAIL_API_KEY = "${{PURELY_MAIL_API_KEY}}"
PURELY_MAIL_DOMAIN = "${{PURELY_MAIL_DOMAIN}}"
CLAWBENCH_CDP_URL = "http://127.0.0.1:9223"
BROWSER_CDP_URL = "http://127.0.0.1:9223"
CDP_URL = "http://127.0.0.1:9223"
CHROME_CDP_URL = "http://127.0.0.1:9223"
PLAYWRIGHT_CDP_URL = "http://127.0.0.1:9223"
CLAWBENCH_NOVNC_URL = "http://127.0.0.1:6080/vnc.html"
CLAWBENCH_RUNTIME_URL = "http://127.0.0.1:7878"
CLAWBENCH_JUDGE_BASE_URL = "${{CLAWBENCH_JUDGE_BASE_URL:-}}"
CLAWBENCH_JUDGE_API_KEY = "${{CLAWBENCH_JUDGE_API_KEY:-}}"
CLAWBENCH_JUDGE_MODEL = "${{CLAWBENCH_JUDGE_MODEL:-deepseek-v4-pro}}"
CLAWBENCH_JUDGE_API_TYPE = "${{CLAWBENCH_JUDGE_API_TYPE:-openai-completions}}"

[[steps]]
name = "{STEP_NAME}"

[steps.agent]
timeout_sec = {float(timeout_sec):.1f}

[steps.verifier]
timeout_sec = 180.0

[steps.healthcheck]
command = "curl -sf http://127.0.0.1:7878/api/status | grep -q '\\\"eval_interceptor_ready\\\":true' && curl -sf http://127.0.0.1:9223/json/version >/dev/null"
interval_sec = 2.0
timeout_sec = 5.0
start_period_sec = 2.0
start_interval_sec = 1.0
retries = 30
"""


def setup_script() -> str:
    return """#!/bin/bash
set -euo pipefail

mkdir -p /data /logs/verifier /app/extra_info
cp /app/eval-schema.json /eval-schema.json

/app/src/runtime-server/.venv/bin/python /app/src/harbor/prepare-task.py \
  --task-json /app/task.json \
  --extra-info-dir /app/extra_info \
  --output-dir /app/my-info

/app/src/harbor/start-runtime.sh

for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:7878/api/status >/dev/null \
    && curl -sf http://127.0.0.1:9223/json/version >/dev/null; then
    rm -f /app/setup.sh
    exit 0
  fi
  sleep 1
done

echo "ClawBench Harbor runtime did not become ready" >&2
exit 1
"""


def test_script() -> str:
    return """#!/bin/bash
set -euo pipefail

curl -sf -X POST http://127.0.0.1:7878/api/stop || true
curl -sf -X POST http://127.0.0.1:7878/api/stop-recording || true
sleep 2
rm -f /data/.stop-requested
rm -rf /logs/verifier/data
cp -a /data /logs/verifier/data

/app/src/runtime-server/.venv/bin/python /app/src/harbor/verify.py
/app/src/runtime-server/.venv/bin/python /app/src/harbor/cleanup-email.py || true
"""


def solve_script() -> str:
    return """#!/bin/bash
set -euo pipefail
echo "ClawBench web tasks do not include oracle browser solutions."
"""


def write_text_executable(path: Path, text: str) -> None:
    path.write_text(text)
    chmod_executable(path)


def copy_extra_info(task: dict[str, Any], task_dir: Path, out_dir: Path) -> None:
    entries = task.get("extra_info") or []
    for item in entries:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        rel = Path(item["path"])
        src = task_dir / rel
        if not src.is_file():
            continue
        dest = out_dir / rel.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def write_harbor_task(
    *,
    task_dir: Path,
    task: dict[str, Any],
    output_root: Path,
    output_name: str,
    org: str,
    dataset_name: str,
) -> Path:
    dest = output_root / output_name
    if dest.exists():
        shutil.rmtree(dest)
    env_dir = dest / "environment"
    step_dir = dest / "steps" / STEP_NAME
    workdir = step_dir / "workdir"
    tests_dir = step_dir / "tests"
    solution_dir = step_dir / "solution"
    for path in (env_dir, workdir, tests_dir, solution_dir):
        path.mkdir(parents=True, exist_ok=True)

    raw_metadata = task.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    description = str(
        metadata.get("description") or task.get("instruction") or task_dir.name
    )
    timeout_sec = int(float(task["time_limit"]) * 60)
    package_name = f"{sanitize_task_name(org)}/{output_name}"

    (dest / "task.toml").write_text(
        task_toml(
            package_name=package_name,
            description=description,
            dataset_name=dataset_name,
            timeout_sec=timeout_sec,
            task_dir_name=task_dir.name,
        )
    )
    (step_dir / "instruction.md").write_text(harbor_instruction(task))
    (workdir / "eval-schema.json").write_text(json.dumps(task["eval_schema"], indent=2))
    (workdir / "task.json").write_text(json.dumps(task, indent=2, ensure_ascii=False))
    copy_extra_info(task, task_dir, workdir / "extra_info")
    write_text_executable(workdir / "setup.sh", setup_script())
    (tests_dir / "task.json").write_text(json.dumps(task, indent=2, ensure_ascii=False))
    write_text_executable(tests_dir / "test.sh", test_script())
    write_text_executable(solution_dir / "solve.sh", solve_script())
    copy_environment(env_dir)
    return dest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert ClawBench V2 task directories into Harbor tasks"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory to write the Harbor dataset",
    )
    parser.add_argument(
        "--cases-dir",
        type=Path,
        default=None,
        help="ClawBench cases directory (defaults to bundled/source test-cases/v2)",
    )
    parser.add_argument("--org", default="clawbench", help="Harbor package org prefix")
    parser.add_argument(
        "--dataset-name", default="v2", help="Dataset name stored in metadata"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Convert at most this many tasks"
    )
    parser.add_argument(
        "--task-ids",
        default="",
        help="Comma-separated task ids or directory names to convert",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing output directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cases_dir = (args.cases_dir or DEFAULT_CASES_DIR).resolve()
    default_cases = args.cases_dir is None
    if not cases_dir.exists():
        parser.error(f"cases directory not found: {cases_dir}")
    if default_cases and cases_dir.name != "v2":
        parser.error("default Harbor adapter supports only ClawBench V2")
    if args.cases_dir is not None and cases_dir.name != "v2":
        print(
            f"WARNING: Harbor support is validated for V2 only; converting explicit cases dir {cases_dir}",
            file=sys.stderr,
        )

    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        if not args.overwrite:
            parser.error(f"output directory exists; pass --overwrite: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    requested = {item.strip() for item in args.task_ids.split(",") if item.strip()}
    cases = discover_cases(cases_dir, requested)
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        parser.error("no matching V2 task.json files found")

    seen: set[str] = set()
    written: list[Path] = []
    for task_dir, task in cases:
        out_name = unique_output_name(task_dir, seen)
        written.append(
            write_harbor_task(
                task_dir=task_dir,
                task=task,
                output_root=output_dir,
                output_name=out_name,
                org=args.org,
                dataset_name=args.dataset_name,
            )
        )

    print(f"Wrote {len(written)} Harbor task(s) to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
