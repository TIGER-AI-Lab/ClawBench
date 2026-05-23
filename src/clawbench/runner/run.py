"""ClawBench single test-case driver."""

import argparse
import hashlib
import json
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.config import (
    BASE_IMAGE,
    DEFAULT_HARNESS,
    ENGINE,
    HARNESSES,
    IMAGE,
    WORKSPACE_ROOT,
    harness_image,
    load_model_config,
    load_runtime_env,
    resolve_task_file,
)
from clawbench.runner.run_support.docker import (
    console,
    docker_build,
    docker_copy,
    docker_logs,
    docker_rm,
    docker_run,
    docker_run_human,
    docker_wait,
    fix_data_ownership as _fix_data_ownership,
    pick_free_port as _pick_free_port,
    step,
)
from clawbench.runner.run_support.email import create_email, delete_email
from clawbench.runner.run_support.metadata import make_run_meta, write_run_meta
from clawbench.runner.run_support.results import (
    classify_run,
    ensure_interception,
    print_results,
)
from clawbench.runner.run_support.task import (
    build_instruction,
    copy_extra_info,
    prepare_personal_info,
    validate_task_data,
)
from clawbench.utils.hf_upload import hf_upload_enabled, upload_run
from clawbench.utils.paths import SHARED_ROOT, ensure_workspace_templates

__all__ = [
    "BASE_IMAGE",
    "DEFAULT_HARNESS",
    "ENGINE",
    "HARNESSES",
    "IMAGE",
    "docker_build",
    "harness_image",
    "main",
]


def main():
    ensure_workspace_templates()

    parser = argparse.ArgumentParser(description="Run a single ClawBench test case")
    parser.add_argument(
        "test_case_dir", type=Path, help="Path to the test case directory"
    )
    parser.add_argument(
        "model",
        type=str,
        nargs="?",
        default=None,
        help="Model name (key in models/models.yaml, required for agent mode)",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Human mode: expose Chrome via noVNC instead of running an agent",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=None,
        help="Directory to write output data to (default: <project>/test-output)",
    )
    parser.add_argument(
        "--no-build",
        dest="no_build",
        action="store_true",
        help="Skip building the container image (assumes it already exists)",
    )
    parser.add_argument(
        "--no-upload",
        dest="no_upload",
        action="store_true",
        help="Skip HuggingFace upload even if HF_TOKEN is configured",
    )
    parser.add_argument(
        "--harness",
        choices=HARNESSES,
        default=DEFAULT_HARNESS,
        help=f"Coding-agent harness (default: {DEFAULT_HARNESS})",
    )
    parser.add_argument(
        "--judge",
        default="deepseek-v4-pro",
        help=(
            "Model name (key in models/models.yaml) used as LLM judge over the "
            "intercepted HTTP request. Pass = intercepted AND judge says match. "
            "Default: deepseek-v4-pro. Use --no-judge to disable."
        ),
    )
    parser.add_argument(
        "--no-judge",
        dest="no_judge",
        action="store_true",
        help="Skip the LLM judge stage; pass = intercepted (stage 1 only)",
    )
    args = parser.parse_args()

    if not args.human and args.model is None:
        parser.error("model is required for agent mode (or use --human)")

    # Load infrastructure config from .env (PurelyMail only)
    env = load_runtime_env()
    infra_required = ["PURELY_MAIL_API_KEY", "PURELY_MAIL_DOMAIN"]
    missing = [k for k in infra_required if not env.get(k)]
    if missing:
        for k in missing:
            print(f"ERROR: {k} not set in .env")
        sys.exit(1)
    pm_key: str = env["PURELY_MAIL_API_KEY"]
    pm_domain: str = env["PURELY_MAIL_DOMAIN"]

    # HuggingFace upload (optional)
    hf_env = {
        "HF_TOKEN": env.get("HF_TOKEN", ""),
        "HF_REPO_ID": env.get("HF_REPO_ID", ""),
    }
    do_upload = hf_upload_enabled(hf_env) and not args.no_upload

    start_time = time.time()
    task_dir, task_file, case_name = resolve_task_file(args.test_case_dir)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    model_cfg: dict | None = None
    if args.human:
        safe_model = "human"
        harness_tag = "human"
    else:
        model_cfg = load_model_config(args.model)
        safe_model = re.sub(r"[/:]+", "--", args.model)
        harness_tag = args.harness

    container = f"clawbench-{harness_tag}-{case_name}-{safe_model}-{int(time.time())}"
    run_dir_name = f"{harness_tag}-{case_name}-{safe_model}-{ts}"

    if args.output_dir is not None:
        output_dir = args.output_dir.resolve() / safe_model / run_dir_name
    else:
        output_dir = WORKSPACE_ROOT / "test-output" / safe_model / run_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)

    task: dict | None = None
    task_json_sha256: str | None = None
    time_limit_s = 1800
    extra_info_warnings: list[str] = []
    intercepted = False
    host_port: int | None = None
    judge_cfg: dict | None = None
    personal_info_metadata: dict[str, Any] | None = None

    # Load and validate task after output_dir exists so task-data failures
    # still leave a run-meta.json for batch/report classification.
    try:
        if not task_file.exists():
            raise FileNotFoundError(f"{task_file} not found")
        task_bytes = task_file.read_bytes()
        loaded_task = json.loads(task_bytes)
        task = validate_task_data(loaded_task, task_file)
        task_json_sha256 = hashlib.sha256(task_bytes).hexdigest()
        time_limit_s = int(float(task["time_limit"]) * 60)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        duration = time.time() - start_time
        classification = classify_run(
            output_dir, False, "task_data", model_cfg=model_cfg
        )
        meta = make_run_meta(
            task=task,
            task_json_sha256=task_json_sha256,
            case_name=case_name,
            args=args,
            model_cfg=model_cfg,
            judge_cfg=judge_cfg,
            task_dir=task_dir,
            task_file=task_file,
            output_dir=output_dir,
            container=container,
            run_dir_name=run_dir_name,
            host_port=host_port,
            email=None,
            ts=ts,
            duration=duration,
            intercepted=False,
            classification=classification,
            failure_reason=f"task_data: {e}",
        )
        write_run_meta(output_dir, meta)
        print(f"ERROR: task_data: {e}")
        sys.exit(2)

    if not args.no_build:
        step("Building container image")
        try:
            docker_build(args.harness)
        except SystemExit as e:
            duration = time.time() - start_time
            classification = classify_run(
                output_dir, False, "infra_failure", model_cfg=model_cfg
            )
            meta = make_run_meta(
                task=task,
                task_json_sha256=task_json_sha256,
                case_name=case_name,
                args=args,
                model_cfg=model_cfg,
                judge_cfg=judge_cfg,
                task_dir=task_dir,
                task_file=task_file,
                output_dir=output_dir,
                container=container,
                run_dir_name=run_dir_name,
                host_port=host_port,
                email=None,
                ts=ts,
                duration=duration,
                intercepted=False,
                classification=classification,
                failure_reason=f"infra_failure: container build exited {e.code}",
            )
            write_run_meta(output_dir, meta)
            raise

    email = None
    personal_info_tmp: Path | None = None
    phase = "startup"
    try:
        assert task is not None

        phase = "creating_email"
        step("Creating disposable email")
        email, email_pw = create_email(pm_key, pm_domain)

        phase = "preparing_personal_info"
        step("Preparing personal info")
        personal_info_tmp, personal_info_metadata = prepare_personal_info(
            SHARED_ROOT, email, email_pw, output_dir
        )
        extra_info_warnings = copy_extra_info(task, task_dir, personal_info_tmp)
        print(f"  Personal info dir: {personal_info_tmp}")

        # Write eval schema for the interceptor
        phase = "writing_eval_schema"
        schema_path = output_dir / "eval-schema.json"
        schema_path.write_text(json.dumps(task["eval_schema"], indent=2))

        phase = "building_instruction"
        step("Building instruction")
        instruction = build_instruction(task)
        print(instruction[:500])

        if args.human:
            phase = "starting_container"
            step("Starting container (human mode)")
            # Avoid hard-coded 6080:6080 collisions under concurrent runs.
            host_port = _pick_free_port(6080)
            docker_run_human(
                container,
                instruction,
                schema_path,
                personal_info_tmp,
                time_limit_s,
                host_port=host_port,
            )

            # Graceful stop on Ctrl+C: give container time to flush recording
            def handle_sigint(sig, frame):
                print("\nCtrl+C received, stopping container gracefully...")
                subprocess.run(
                    [ENGINE, "stop", "-t", "20", container], capture_output=True
                )

            signal.signal(signal.SIGINT, handle_sigint)

            vnc_url = f"http://localhost:{host_port}/vnc.html"
            console.print(f"\n  noVNC: [link={vnc_url}]{vnc_url}[/link]")
            if host_port != 6080:
                console.print(
                    f"  [dim](port 6080 was busy, auto-picked {host_port})[/dim]"
                )
            console.print(f"  Task:  {task['instruction'][:200]}")
            console.print(f"  Email: {email}  Password: {email_pw}")
            console.print(f"  Time limit: {task['time_limit']} minutes")
            console.print("  Close the noVNC tab when done.\n")

            step(f"Waiting for human (max {task['time_limit']}min)")
        else:
            phase = "starting_container"
            step("Starting container")
            assert model_cfg is not None
            host_port = _pick_free_port(6080)
            docker_run(
                container,
                instruction,
                schema_path,
                personal_info_tmp,
                model_cfg,
                time_limit_s=time_limit_s,
                host_port=host_port,
                harness=args.harness,
            )

            vnc_url = f"http://localhost:{host_port}/vnc.html"
            console.print(f"\n  noVNC: [link={vnc_url}]{vnc_url}[/link]")
            if host_port != 6080:
                console.print(
                    f"  [dim](port 6080 was busy, auto-picked {host_port})[/dim]"
                )
            console.print("  Open the URL above to watch the agent in real-time.\n")

            step(f"Agent running (max {task['time_limit']}min)")

        phase = "waiting_for_container"
        docker_wait(
            container,
            model_cfg=None if args.human else model_cfg,
            harness=None if args.human else args.harness,
        )

        phase = "container_logs"
        step("Container logs")
        docker_logs(container)

        phase = "copying_results"
        step("Copying results")
        docker_copy(container, output_dir)
        _fix_data_ownership(output_dir / "data")

        phase = "ensuring_interception"
        ensure_interception(output_dir)

        phase = "printing_results"
        step("Results")
        intercepted = print_results(
            output_dir,
            model_cfg=None if args.human else model_cfg,
        )

        # Stage 2 — LLM judge (default on, --no-judge to skip).
        # Only invoked when stage 1 (intercepted) succeeded; otherwise the
        # task already fails at stage 1 and there's nothing to judge.
        judge_result: dict[str, Any] | None = None
        if intercepted and not args.no_judge and args.judge:
            phase = "running_judge"
            step("LLM judge")
            try:
                from clawbench.runner.judge import judge_request

                judge_cfg = load_model_config(args.judge)
                instruction_text = (
                    task.get("instruction") if isinstance(task, dict) else ""
                ) or ""
                interception_path = output_dir / "data" / "interception.json"
                if interception_path.exists():
                    intercept_blob = json.loads(interception_path.read_text())
                else:
                    intercept_blob = {}
                judge_result = judge_request(
                    judge_cfg,
                    judge_cfg.get("model", args.judge),
                    instruction_text,
                    intercept_blob,
                    judge_context=(
                        task.get("judge_context")
                        if isinstance(task.get("judge_context"), dict)
                        else None
                    ),
                )
                (output_dir / "judge.json").write_text(
                    json.dumps(judge_result, indent=2, ensure_ascii=False)
                )
                print(
                    f"Judge ({args.judge}): "
                    f"match={judge_result.get('match')}  "
                    f"reason={judge_result.get('reason', '')[:160]}"
                )
            except Exception as e:
                judge_result = {
                    "match": None,
                    "reason": f"judge_setup_failed: {e}",
                    "judge_model": args.judge,
                    "raw": None,
                    "error": str(e),
                }
                (output_dir / "judge.json").write_text(
                    json.dumps(judge_result, indent=2, ensure_ascii=False)
                )
                print(f"Judge skipped due to error: {e}")

        # Write run metadata
        phase = "writing_run_meta"
        duration = time.time() - start_time
        classification = classify_run(output_dir, intercepted, model_cfg=model_cfg)
        meta = make_run_meta(
            task=task,
            task_json_sha256=task_json_sha256,
            case_name=case_name,
            args=args,
            model_cfg=model_cfg,
            judge_cfg=judge_cfg,
            task_dir=task_dir,
            task_file=task_file,
            output_dir=output_dir,
            container=container,
            run_dir_name=run_dir_name,
            host_port=host_port,
            personal_info_metadata=personal_info_metadata,
            email=email,
            ts=ts,
            duration=duration,
            intercepted=intercepted,
            classification=classification,
            extra_info_warnings=extra_info_warnings,
        )
        if judge_result is not None:
            meta["judge"] = judge_result
            meta["judge_match"] = judge_result.get("match")
        meta["pass"] = bool(
            intercepted
            and (
                args.no_judge
                or judge_result is None
                or judge_result.get("match") is True
            )
        )
        write_run_meta(output_dir, meta)

        if do_upload:
            phase = "uploading"
            step("Uploading to HuggingFace")
            repo_path = f"{safe_model}/{run_dir_name}"
            upload_run(output_dir, repo_path, hf_env)

    except Exception as e:
        category = "infra_failure"
        if phase == "building_instruction":
            category = "build_instruction"
        elif phase == "writing_eval_schema":
            category = "task_data"
        try:
            if (output_dir / "data").exists():
                ensure_interception(output_dir)
        except Exception:
            pass
        duration = time.time() - start_time
        classification = classify_run(output_dir, False, category, model_cfg=model_cfg)
        meta = make_run_meta(
            task=task,
            task_json_sha256=task_json_sha256,
            case_name=case_name,
            args=args,
            model_cfg=model_cfg,
            judge_cfg=judge_cfg,
            task_dir=task_dir,
            task_file=task_file,
            output_dir=output_dir,
            container=container,
            run_dir_name=run_dir_name,
            host_port=host_port,
            personal_info_metadata=personal_info_metadata,
            email=email,
            ts=ts,
            duration=duration,
            intercepted=False,
            classification=classification,
            failure_reason=f"{category}: {phase}: {type(e).__name__}: {e}",
            extra_info_warnings=extra_info_warnings,
        )
        write_run_meta(output_dir, meta)
        print(f"ERROR: {phase} failed: {e}")
        sys.exit(2)
    finally:
        step("Cleanup")
        docker_rm(container)
        if email:
            delete_email(pm_key, email)
        if personal_info_tmp and personal_info_tmp.exists():
            shutil.rmtree(personal_info_tmp, ignore_errors=True)
        (output_dir / "eval-schema.json").unlink(missing_ok=True)

    # Final pass status: stage 1 (intercepted) AND stage 2 (judge match), unless --no-judge.
    final_pass = bool(meta.get("pass"))
    if not intercepted:
        print(f"\nNOT INTERCEPTED — results in {output_dir}")
        sys.exit(1)
    if (
        not args.no_judge
        and judge_result is not None
        and judge_result.get("match") is not True
    ):
        verdict = judge_result.get("match")
        reason = judge_result.get("reason", "")
        print(
            f"\nINTERCEPTED but JUDGE {'MISMATCH' if verdict is False else 'INCONCLUSIVE'} "
            f"— results in {output_dir}\n  reason: {reason[:200]}"
        )
        sys.exit(1)
    if final_pass:
        print(f"\nINTERCEPTED + JUDGE MATCH — results in {output_dir}")
    else:
        print(f"\nINTERCEPTED — results in {output_dir}")


if __name__ == "__main__":
    main()
