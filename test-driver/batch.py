"""ClawBench batch test driver — run model x case cross-product concurrently."""

import argparse
import asyncio
import fnmatch
import itertools
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def detect_engine() -> str:
    env = os.environ.get("CONTAINER_ENGINE", "").strip().lower()
    if env:
        if env not in ("docker", "podman"):
            print(f"ERROR: CONTAINER_ENGINE must be 'docker' or 'podman', got '{env}'")
            sys.exit(1)
        if not shutil.which(env):
            print(f"ERROR: CONTAINER_ENGINE={env} but '{env}' not found on PATH")
            sys.exit(1)
        return env
    for cmd in ("docker", "podman"):
        if shutil.which(cmd):
            return cmd
    print("ERROR: Neither 'docker' nor 'podman' found on PATH")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

MODELS_YAML = PROJECT_ROOT / "models" / "models.yaml"


def load_models_yaml() -> dict:
    """Load all model definitions from models/models.yaml."""
    if not MODELS_YAML.exists():
        print(f"ERROR: {MODELS_YAML} not found (copy models.example.yaml and fill in your keys)")
        sys.exit(1)
    return yaml.safe_load(MODELS_YAML.read_text()) or {}


def discover_models(patterns: list[str] | None, all_models: bool) -> list[str]:
    models = load_models_yaml()
    if all_models:
        return sorted(models.keys())
    if not patterns:
        print("ERROR: provide --models or --all-models")
        sys.exit(1)
    matched: list[str] = []
    for name in sorted(models.keys()):
        if any(fnmatch.fnmatch(name, pat) for pat in patterns):
            matched.append(name)
    if not matched:
        print(f"ERROR: no models matched patterns: {patterns}")
        print(f"Available models: {', '.join(sorted(models))}")
        sys.exit(1)
    return matched


def _case_id(d: Path) -> int | None:
    """Extract the leading numeric ID from a case directory name (e.g. '042-foo' -> 42)."""
    parts = d.name.split("-", 1)
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return None


def discover_cases(patterns: list[str] | None, all_cases: bool,
                   case_range: str | None = None) -> list[Path]:
    base = PROJECT_ROOT / "test-cases"
    if all_cases:
        dirs = sorted(p.parent for p in base.glob("*/task.json"))
    elif patterns:
        dirs = []
        for pat in patterns:
            expanded = sorted(PROJECT_ROOT.glob(pat))
            for d in expanded:
                if d.is_dir() and (d / "task.json").exists():
                    dirs.append(d)
    elif case_range:
        dirs = sorted(p.parent for p in base.glob("*/task.json"))
    else:
        print("ERROR: provide --cases, --all-cases, or --case-range")
        sys.exit(1)

    # Apply numeric range filter
    if case_range:
        lo, hi = _parse_range(case_range)
        dirs = [d for d in dirs if (cid := _case_id(d)) is not None and lo <= cid <= hi]

    dirs = sorted(set(dirs))
    if not dirs:
        print(f"ERROR: no test-case directories matched (patterns={patterns}, range={case_range})")
        sys.exit(1)
    return dirs


def _parse_range(r: str) -> tuple[int, int]:
    """Parse 'START-END' into (start, end) inclusive."""
    parts = r.split("-", 1)
    if len(parts) != 2:
        print(f"ERROR: --case-range must be START-END (e.g. 1-50), got '{r}'")
        sys.exit(1)
    try:
        lo, hi = int(parts[0]), int(parts[1])
    except ValueError:
        print(f"ERROR: --case-range values must be integers, got '{r}'")
        sys.exit(1)
    if lo > hi:
        print(f"ERROR: --case-range start must be <= end, got '{r}'")
        sys.exit(1)
    return lo, hi


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

@dataclass
class Job:
    model: str
    case_dir: Path
    case_name: str
    status: str = "pending"
    duration: float = 0.0
    proc: asyncio.subprocess.Process | None = field(default=None, repr=False)


def fmt_duration(s: float) -> str:
    m, sec = divmod(int(s), 60)
    return f"{m}m{sec:02d}s"


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Async runner
# ---------------------------------------------------------------------------

shutdown_event: asyncio.Event | None = None
running_procs: list[asyncio.subprocess.Process] = []


class StartupThrottle:
    """Ensure a minimum gap between consecutive container starts.

    Unlike a fixed per-index stagger, this adapts dynamically: whenever a
    semaphore slot frees up, the next job still waits until *min_interval*
    seconds have passed since the last container launch.
    """

    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_start = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self._last_start + self._min_interval - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_start = time.monotonic()


async def run_job(
    job: Job,
    sem: asyncio.Semaphore,
    throttle: StartupThrottle,
    base_output: Path,
    log_dir: Path,
    all_jobs: list[Job],
    batch_start: float,
    no_upload: bool = False,
) -> None:
    assert shutdown_event is not None
    try:
        async with sem:
            if shutdown_event.is_set():
                job.status = "skipped"
                return

            # Throttle container startup to avoid resource spikes
            await throttle.wait()

            # Re-check after throttle wait — Ctrl+C may have fired
            if shutdown_event.is_set():
                job.status = "skipped"
                return

            job.status = "running"
            print(f"[{ts()}] [START] {job.case_name} x {job.model}")
            print_progress(all_jobs, batch_start)

            safe_model = re.sub(r'[/:]+', '--', job.model)
            log_path = log_dir / f"{job.case_name}-{safe_model}.log"
            start = time.monotonic()

            proc: asyncio.subprocess.Process | None = None
            try:
                cmd_parts = [
                    "uv", "run", "--project", "test-driver",
                    "test-driver/run.py",
                    str(job.case_dir), job.model,
                    "--output-dir", str(base_output),
                    "--no-build",
                ]
                if no_upload:
                    cmd_parts.append("--no-upload")
                proc = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(PROJECT_ROOT),
                    start_new_session=True,
                )
                job.proc = proc
                running_procs.append(proc)
                try:
                    stdout, _ = await proc.communicate()
                finally:
                    if proc in running_procs:
                        running_procs.remove(proc)
                    job.proc = None

                job.duration = time.monotonic() - start
                log_path.write_bytes(stdout or b"")

                if proc.returncode == 0:
                    job.status = "passed"
                elif proc.returncode == 1:
                    job.status = "failed"
                else:
                    job.status = "error"
            except asyncio.CancelledError:
                job.duration = time.monotonic() - start
                # Only mark as error if a subprocess was actually running;
                # otherwise leave status for the outer handler to set "skipped".
                if proc is not None:
                    job.status = "error"
                    # Kill subprocess if still alive when we get cancelled.
                    # Use local `proc` — the inner finally already cleared job.proc.
                    if proc.returncode is None:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except (ProcessLookupError, OSError):
                            pass
                        if proc in running_procs:
                            running_procs.remove(proc)
                raise
            except Exception as e:
                job.duration = time.monotonic() - start
                job.status = "error"
                try:
                    log_path.write_text(f"batch.py: failed to run job: {e}\n")
                except OSError:
                    pass

            tag = job.status.upper()
            print(f"[{ts()}] [DONE] {job.case_name} x {job.model}: {tag} in {fmt_duration(job.duration)}")
            print_progress(all_jobs, batch_start)

    except asyncio.CancelledError:
        # Task cancelled while waiting on semaphore, throttle wait, or
        # before subprocess was created.  "running" can appear here if
        # CancelledError hit after status was set but before proc started.
        if job.status not in ("passed", "failed", "error"):
            job.status = "skipped"
        raise


def print_progress(jobs: list[Job], start: float) -> None:
    done = sum(1 for j in jobs if j.status not in ("pending", "running"))
    running = sum(1 for j in jobs if j.status == "running")
    passed = sum(1 for j in jobs if j.status == "passed")
    failed = sum(1 for j in jobs if j.status in ("failed", "error"))
    elapsed = fmt_duration(time.monotonic() - start)
    print(
        f"[{ts()}] [BATCH] {done}/{len(jobs)} done | {running} running | "
        f"{passed} passed, {failed} failed | {elapsed} elapsed",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(jobs: list[Job], elapsed: float, max_concurrent: int) -> None:
    print(f"\n{'=' * 60}")
    print("BATCH SUMMARY")
    print(f"{'=' * 60}")

    model_w = max((len(j.model) for j in jobs), default=5)
    case_w = max((len(j.case_name) for j in jobs), default=4)
    header = f"{'Model':<{model_w}}  {'Case':<{case_w}}  Status  Duration"
    print(header)
    print("-" * len(header))
    for j in jobs:
        tag = j.status.upper()
        print(f"{j.model:<{model_w}}  {j.case_name:<{case_w}}  {tag:<7}  {fmt_duration(j.duration)}")

    totals = {}
    for j in jobs:
        totals[j.status] = totals.get(j.status, 0) + 1
    parts = [f"{totals.get(s, 0)} {s}" for s in ("passed", "failed", "error", "skipped") if totals.get(s)]
    print(f"\nTotal: {len(jobs)} jobs | {' | '.join(parts)}")
    print(f"Total elapsed: {fmt_duration(elapsed)} (max_concurrent={max_concurrent})")


def print_run_stats(base_output: Path) -> None:
    """Print per-run statistics from output directories."""
    print(f"\n{'=' * 80}")
    print("PER-RUN STATS")
    print(f"{'=' * 80}")

    rows = []
    for model_dir in sorted(base_output.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("batch-"):
            continue
        for run_dir in sorted(model_dir.iterdir()):
            if not run_dir.is_dir():
                continue
            data = run_dir / "data"
            if not data.exists():
                continue

            # Parse case and model from run-meta.json or dir name
            meta_file = run_dir / "run-meta.json"
            if meta_file.exists():
                meta = json.loads(meta_file.read_text())
                case = meta.get("test_case", "?")
                model = meta.get("model", model_dir.name)
                intercepted = meta.get("intercepted", False)
                duration = meta.get("duration_seconds", 0)
            else:
                case = run_dir.name
                model = model_dir.name
                intercepted = False
                duration = 0

            # Count actions
            actions_file = data / "actions.jsonl"
            actions = sum(1 for _ in open(actions_file)) if actions_file.exists() and actions_file.stat().st_size > 0 else 0

            # Count screenshots
            ss_dir = data / "screenshots"
            screenshots = len(list(ss_dir.iterdir())) if ss_dir.is_dir() else 0

            # Recording size
            rec = data / "recording.mp4"
            rec_mb = rec.stat().st_size / (1024 * 1024) if rec.exists() else 0

            rows.append({
                "case": case, "model": model, "actions": actions,
                "screenshots": screenshots, "recording_mb": rec_mb,
                "duration": duration, "intercepted": intercepted,
            })

    if not rows:
        print("  No run data found.")
        return

    RED = "\033[91m"
    RESET = "\033[0m"

    case_w = min(max(len(r["case"]) for r in rows), 50)
    model_w = max(len(r["model"]) for r in rows)
    header = f"{'Case':<{case_w}}  {'Model':<{model_w}}  Actions  Screenshots  Recording   Duration  Intercepted"
    print(header)
    print("-" * len(header))
    for r in rows:
        result = "yes" if r["intercepted"] else "no"
        case = r["case"][:case_w]
        # Flag abnormal runs: no actions, no screenshots, no recording, or very short duration
        abnormal = (r["actions"] == 0 or r["screenshots"] == 0
                    or r["recording_mb"] < 0.5 or r["duration"] < 30)
        line = (
            f"{case:<{case_w}}  {r['model']:<{model_w}}  "
            f"{r['actions']:>7}  {r['screenshots']:>11}  "
            f"{r['recording_mb']:>7.1f} MB  "
            f"{fmt_duration(r['duration']):>8}  {result}"
        )
        if abnormal:
            print(f"{RED}{line}{RESET}")
        else:
            print(line)

    total_pass = sum(1 for r in rows if r["intercepted"])
    abnormal_count = sum(1 for r in rows if r["actions"] == 0 or r["screenshots"] == 0
                         or r["recording_mb"] < 0.5 or r["duration"] < 30)
    print(f"\n{total_pass}/{len(rows)} intercepted", end="")
    if abnormal_count:
        print(f"  |  {RED}{abnormal_count} abnormal{RESET}")
    else:
        print()


def write_summary_json(jobs: list[Job], base_output: Path, elapsed: float,
                       max_concurrent: int, started_at: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "started_at": started_at,
        "finished_at": now,
        "elapsed_seconds": round(elapsed),
        "max_concurrent": max_concurrent,
        "jobs": [
            {
                "model": j.model,
                "case": j.case_name,
                "status": j.status,
                "duration_seconds": round(j.duration),
            }
            for j in jobs
        ],
        "totals": {
            s: sum(1 for j in jobs if j.status == s)
            for s in ("passed", "failed", "error", "skipped")
        },
    }
    (base_output / "batch-summary.json").write_text(json.dumps(data, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main(args: argparse.Namespace) -> int:
    global shutdown_event
    shutdown_event = asyncio.Event()
    running_procs.clear()

    models = discover_models(args.models, args.all_models)
    cases = discover_cases(args.cases, args.all_cases, args.case_range)

    # Interleave models: iterate cases in the outer loop so consecutive jobs
    # hit different API providers, reducing the chance of draining one API.
    jobs = [
        Job(model=m, case_dir=c, case_name=c.name)
        for c, m in itertools.product(cases, models)
    ]

    if not jobs:
        print("No jobs to run.")
        return 0

    print(f"Job matrix: {len(models)} model(s) x {len(cases)} case(s) = {len(jobs)} job(s)")
    for j in jobs:
        print(f"  {j.case_name} x {j.model}")

    if args.dry_run:
        return 0

    # Build image once
    engine = detect_engine()
    # Ensure child run.py processes use the same engine
    os.environ["CONTAINER_ENGINE"] = engine
    print(f"\nBuilding Docker image (engine={engine})...")
    subprocess.run([engine, "build", "-t", "clawbench", str(PROJECT_ROOT)], check=True)

    batch_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_output = Path(args.output_dir).resolve() / f"batch-{batch_ts}"
    log_dir = base_output / "batch-logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    sem = asyncio.Semaphore(args.max_concurrent)
    batch_start = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()

    # Signal handling — asyncio-native
    sigint_count = 0
    all_tasks: list[asyncio.Task] = []
    loop = asyncio.get_running_loop()

    def on_signal() -> None:
        nonlocal sigint_count
        sigint_count += 1
        shutdown_event.set()

        if sigint_count == 1:
            n_running = sum(1 for j in jobs if j.status == "running")
            print(f"\n[BATCH] Stopping — no new jobs will start. "
                  f"Waiting for {n_running} running job(s) to finish...")
            print("[BATCH] Press Ctrl+C again to kill running jobs.")
            # Cancel only non-running tasks so no new jobs start.
            # Running tasks are left alone — they'll finish naturally
            # and their run.py subprocesses will clean up containers.
            for j, t in zip(jobs, all_tasks):
                if j.status != "running" and not t.done():
                    t.cancel()
        else:
            n_running = sum(1 for p in running_procs if p.returncode is None)
            print(f"\n[BATCH] Killing {n_running} running job(s)...")
            for proc in list(running_procs):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
            for t in all_tasks:
                if not t.done():
                    t.cancel()

    loop.add_signal_handler(signal.SIGINT, on_signal)
    loop.add_signal_handler(signal.SIGTERM, on_signal)

    throttle = StartupThrottle(args.stagger_delay)
    all_tasks = [
        asyncio.create_task(
            run_job(j, sem, throttle, base_output, log_dir, jobs, batch_start,
                    no_upload=args.no_upload)
        )
        for j in jobs
    ]

    results = await asyncio.gather(*all_tasks, return_exceptions=True)

    # Mark cancelled jobs as skipped
    for j, r in zip(jobs, results):
        if isinstance(r, asyncio.CancelledError) and j.status == "pending":
            j.status = "skipped"

    # Restore default signal handling for cleanup phase
    loop.remove_signal_handler(signal.SIGINT)
    loop.remove_signal_handler(signal.SIGTERM)

    elapsed = time.monotonic() - batch_start
    print_summary(jobs, elapsed, args.max_concurrent)
    print_run_stats(base_output)
    write_summary_json(jobs, base_output, elapsed, args.max_concurrent, started_at)
    print(f"\nSummary written to {base_output / 'batch-summary.json'}")

    # Upload batch summary to HuggingFace
    if not args.no_upload:
        from run import load_dotenv
        from hf_upload import hf_upload_enabled, upload_file
        env = load_dotenv(PROJECT_ROOT / ".env")
        hf_env = {"HF_TOKEN": env.get("HF_TOKEN", ""), "HF_REPO_ID": env.get("HF_REPO_ID", "")}
        if hf_upload_enabled(hf_env):
            safe_ts = started_at.replace(":", "-")
            upload_file(
                base_output / "batch-summary.json",
                f"batch-summaries/{safe_ts}-batch-summary.json",
                hf_env,
            )

    has_errors = any(j.status == "error" for j in jobs)
    return 1 if has_errors else 0


def main() -> None:
    p = argparse.ArgumentParser(description="Run ClawBench model x case cross-product")
    p.add_argument("--models", nargs="+", default=None, help="Model name patterns (matched against keys in models/models.yaml)")
    p.add_argument("--all-models", action="store_true", help="Use all models in models/models.yaml")
    p.add_argument("--cases", nargs="+", default=None, help="Glob patterns for case dirs")
    p.add_argument("--all-cases", action="store_true", help="Use all test-cases/ subdirs")
    p.add_argument("--case-range", default=None, help="Numeric ID range, e.g. 1-50")
    p.add_argument("--max-concurrent", type=int, default=2, help="Max parallel jobs (default: 2)")
    p.add_argument("--output-dir", default="test-output", help="Base output directory")
    p.add_argument("--stagger-delay", type=float, default=15,
                   help="Min seconds between consecutive container starts — rolling start (default: 15)")
    p.add_argument("--dry-run", action="store_true", help="Print job matrix without running")
    p.add_argument("--no-upload", dest="no_upload", action="store_true",
                   help="Skip HuggingFace upload for all runs")
    args = p.parse_args()

    rc = asyncio.run(async_main(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
