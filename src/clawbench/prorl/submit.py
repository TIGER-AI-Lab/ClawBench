"""``clawbench-prorl-submit`` — submit a ClawBench task to Polar as an RL rollout.

Stages a ClawBench V2 task with the existing Harbor adapter (instruction + a
``tests/test.sh`` that writes ``/logs/verifier/reward.json``), wraps it in a
Polar ``TaskRequest`` (shell harness + ``harbor`` evaluator), and drives
submit / poll / read-reward against a Rollout Server.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from clawbench.eval.harbor_adapter import (
    DEFAULT_CASES_DIR,
    STEP_NAME,
    discover_cases,
    sanitize_task_name,
    write_harbor_task,
)
from clawbench.utils.paths import RUNTIME_ROOT
from clawbench.prorl.models import (
    AgentSpec,
    BuilderSpec,
    EvaluatorSpec,
    PrepareAction,
    RuntimeSpec,
    TaskRequest,
)

RUN_SCRIPT = Path(__file__).resolve().parent / "run-prorl.sh"

# Terminal Polar task states. Only "completed" is success; the rest are failures.
TERMINAL_OK = {"completed"}
TERMINAL_ERROR = {"failed", "error", "timeout", "cancelled"}
NONTERMINAL = {"running", "pending", "queued", "dispatched"}

# Judge (Stage-2) env keys read by the verifier; carried in the evaluator env,
# never derived from the gateway-injected OPENAI_* (would pollute the trajectory).
JUDGE_ENV_KEYS = {
    "model": "CLAWBENCH_JUDGE_MODEL",
    "base_url": "CLAWBENCH_JUDGE_BASE_URL",
    "api_key": "CLAWBENCH_JUDGE_API_KEY",
    "api_type": "CLAWBENCH_JUDGE_API_TYPE",
}


def stage_task(
    task_dir: Path,
    task: dict[str, Any],
    staging_root: Path,
    *,
    org: str,
    dataset_name: str,
    output_name: str,
) -> Path:
    """Stage one task into a Harbor package layout; return the package dir."""
    return write_harbor_task(
        task_dir=task_dir,
        task=task,
        output_root=staging_root,
        output_name=output_name,
        org=org,
        dataset_name=dataset_name,
    )


def build_task_request(
    staged: Path,
    *,
    task_id: str,
    image: str,
    model_name: str,
    num_samples: int,
    timeout_seconds: int,
    dataset_name: str,
    judge_env: dict[str, str] | None = None,
) -> TaskRequest:
    """Build the Polar ``TaskRequest`` for a staged ClawBench task."""
    step_dir = staged / "steps" / STEP_NAME
    workdir = step_dir / "workdir"
    tests_dir = step_dir / "tests"
    instruction = (step_dir / "instruction.md").read_text()

    # Seed the session: stage the task workdir + run script + instruction, upload
    # the Harbor runtime scripts the staged setup.sh/verify.py reference (so a
    # plain ClawBench harness image — base + harness + runtime-server — works
    # without a bespoke combined image), then bring up the browser runtime via
    # the task's own setup.sh.
    prepare = [
        PrepareAction(type="upload_dir", source=str(workdir), target="/app"),
        PrepareAction(
            type="upload_dir",
            source=str(RUNTIME_ROOT / "harbor"),
            target="/app/src/harbor",
        ),
        PrepareAction(
            type="upload_file", source=str(RUN_SCRIPT), target="/app/run-prorl.sh"
        ),
        PrepareAction(
            type="upload_file",
            source=str(step_dir / "instruction.md"),
            target="/app/instruction.md",
        ),
        PrepareAction(type="exec", command="bash /app/setup.sh", cwd="/app"),
    ]

    runtime = RuntimeSpec(image=image, prepare=prepare)

    # Shell harness: the browser episode, with the policy model routed through
    # the gateway-injected $OPENAI_BASE_URL (captured into the trajectory).
    agent = AgentSpec(
        model_name=model_name,
        harness="shell",
        custom_shell={"command": "bash /app/run-prorl.sh", "cwd": "/app"},
        env={
            "POLAR_MODEL_NAME": model_name,
            "CLAWBENCH_INSTRUCTION_FILE": "/app/instruction.md",
        },
    )

    # Reward: Polar's built-in harbor evaluator runs our tests/test.sh, which
    # runs the two-stage scorer and writes /logs/verifier/reward.json. The judge
    # (Stage-2) config is carried in the evaluator env — independent of the
    # policy's OPENAI_* endpoint — so judging actually runs during rollouts.
    evaluator = EvaluatorSpec(
        strategy="harbor",
        config={
            "tests_dir": str(tests_dir),
            "tests_target": "/tests",
            "verifier_dir": "/logs/verifier",
            "test_command": "bash /tests/test.sh",
            "verifier_timeout": 180,
        },
        refresh_runtime=False,
        env=judge_env or None,
    )

    return TaskRequest(
        task_id=task_id,
        instruction=instruction,
        runtime=runtime,
        agent=agent,
        evaluator=evaluator,
        builder=BuilderSpec(strategy="prefix_merging"),
        num_samples=num_samples,
        timeout_seconds=timeout_seconds,
        metadata={"clawbench_task": task_id, "dataset": dataset_name},
    )


# ---------------------------------------------------------------------------
# Rollout Server client (stdlib only)
# ---------------------------------------------------------------------------


def _post_json(
    url: str, payload: dict[str, Any], timeout: float = 30.0
) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted host)
        return json.loads(resp.read().decode())


def _get_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


def submit_task(rollout_url: str, payload: dict[str, Any]) -> str:
    result = _post_json(rollout_url.rstrip("/") + "/rollout/task/submit", payload)
    task_id = result.get("task_id")
    if not task_id:
        raise RuntimeError(f"submit did not return a task_id: {result}")
    return str(task_id)


def poll_task(
    rollout_url: str, task_id: str, *, interval: float = 3.0, max_wait: float = 3600.0
) -> dict[str, Any]:
    url = f"{rollout_url.rstrip('/')}/rollout/task/{task_id}"
    waited = 0.0
    while True:
        status = _get_json(url)
        state = str(status.get("status", "")).lower()
        if state in TERMINAL_OK:
            return status
        if state in TERMINAL_ERROR:
            raise RuntimeError(
                f"task {task_id} ended in state {state!r}: {status.get('error') or status}"
            )
        if state not in NONTERMINAL:
            raise RuntimeError(f"task {task_id} returned unexpected status {state!r}")
        if waited >= max_wait:
            raise TimeoutError(f"task {task_id} still {state} after {max_wait}s")
        time.sleep(interval)
        waited += interval


def extract_rewards(status: dict[str, Any]) -> list[float]:
    """Pull per-session final-trace rewards out of a completed TaskStatus."""
    rewards: list[float] = []
    for session in status.get("sessions", []) or []:
        traj = session.get("trajectory") or {}
        traces = traj.get("traces") or []
        if traces and traces[-1].get("reward") is not None:
            rewards.append(float(traces[-1]["reward"]))
    return rewards


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawbench-prorl-submit",
        description="Submit a ClawBench V2 task to ProRL-Agent-Server (Polar) as an RL rollout.",
    )
    p.add_argument(
        "--task", required=True, help="ClawBench task id (dir name under the cases dir)"
    )
    p.add_argument(
        "--cases-dir", type=Path, default=None, help="V2 cases dir (default: bundled)"
    )
    p.add_argument(
        "--rollout-url", default="http://127.0.0.1:8080", help="Rollout Server URL"
    )
    p.add_argument(
        "--image",
        default=None,
        help="ClawBench runtime image (must bundle a harness + browser runtime); "
        "default: clawbench-<harness>:latest",
    )
    p.add_argument(
        "--model-name",
        default="clawbench-policy",
        help="Policy model name sent by the harness",
    )
    p.add_argument("--judge-model", default=None, help="Stage-2 judge model name")
    p.add_argument(
        "--judge-base-url",
        default=None,
        help="Stage-2 judge base URL (NOT the policy endpoint)",
    )
    p.add_argument("--judge-api-key", default=None, help="Stage-2 judge API key")
    p.add_argument("--judge-api-type", default=None, help="Stage-2 judge api_type")
    p.add_argument(
        "--num-samples",
        type=int,
        default=8,
        help="Rollout sessions per task (GRPO group size)",
    )
    p.add_argument("--timeout", type=int, default=900, help="Per-session timeout (s)")
    p.add_argument(
        "--harness",
        default="hermes",
        help="ClawBench browser harness to drive the episode",
    )
    p.add_argument("--org", default="clawbench", help="Package org prefix")
    p.add_argument(
        "--dataset-name", default="clawbench-v2", help="Dataset label in metadata"
    )
    p.add_argument(
        "--staging-dir",
        type=Path,
        default=None,
        help="Where to stage the task (default: temp)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the TaskRequest payload; do not submit",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cases_dir = (args.cases_dir or DEFAULT_CASES_DIR).resolve()
    if not cases_dir.exists():
        print(f"ERROR: cases directory not found: {cases_dir}", file=sys.stderr)
        return 1
    cases = discover_cases(cases_dir, {args.task})
    if not cases:
        print(f"ERROR: task {args.task!r} not found under {cases_dir}", file=sys.stderr)
        return 1
    task_dir, task = cases[0]

    image = args.image or f"clawbench-{args.harness}:latest"
    judge_env = {
        env_key: getattr(args, f"judge_{arg}")
        for arg, env_key in JUDGE_ENV_KEYS.items()
        if getattr(args, f"judge_{arg}")
    }
    if not args.dry_run and not judge_env:
        print(
            "WARNING: no --judge-* config given; the Stage-2 judge will be "
            "unconfigured and rewards may fall to 0.0. Pass "
            "--judge-model/--judge-base-url/--judge-api-key, or use a "
            "Stage-1-only test.sh.",
            file=sys.stderr,
        )

    import tempfile
    from contextlib import ExitStack

    with ExitStack() as stack:
        if args.staging_dir:
            staging_root = args.staging_dir
            staging_root.mkdir(parents=True, exist_ok=True)
        else:
            staging_root = Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="clawbench-prorl-")
                )
            )
        output_name = sanitize_task_name(task_dir.name)
        staged = stage_task(
            task_dir,
            task,
            staging_root,
            org=args.org,
            dataset_name=args.dataset_name,
            output_name=output_name,
        )

        request = build_task_request(
            staged,
            task_id=task_dir.name,
            image=image,
            model_name=args.model_name,
            num_samples=args.num_samples,
            timeout_seconds=args.timeout,
            dataset_name=args.dataset_name,
            judge_env=judge_env or None,
        )
        payload = request.to_payload()

        if args.dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        try:
            task_id = submit_task(args.rollout_url, payload)
            print(
                f"submitted task {task_id}; polling {args.rollout_url} ...",
                file=sys.stderr,
            )
            status = poll_task(args.rollout_url, task_id)
        except (urllib.error.URLError, TimeoutError, RuntimeError) as e:
            print(f"ERROR: rollout failed: {e}", file=sys.stderr)
            return 1

        rewards = extract_rewards(status)
        mean = sum(rewards) / len(rewards) if rewards else 0.0
        print(
            json.dumps(
                {
                    "task": task_dir.name,
                    "status": status.get("status"),
                    "num_sessions": len(rewards),
                    "rewards": rewards,
                    "mean_reward": mean,
                },
                indent=2,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
