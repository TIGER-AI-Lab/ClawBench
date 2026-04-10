"""ClawBench single test-case driver."""

import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml

from generate_resume_pdf import generate_resume_pdf
from hf_upload import hf_upload_enabled, upload_run

PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE = "clawbench"


def _detect_engine() -> str:
    env = os.environ.get("CONTAINER_ENGINE", "").strip().lower()
    if env:
        if env not in ("docker", "podman"):
            print(
                f"ERROR: CONTAINER_ENGINE must be 'docker' or 'podman', got '{env}'")
            sys.exit(1)
        if not shutil.which(env):
            print(
                f"ERROR: CONTAINER_ENGINE={env} but '{env}' not found on PATH")
            sys.exit(1)
        return env
    for cmd in ("docker", "podman"):
        if shutil.which(cmd):
            return cmd
    print("ERROR: Neither 'podman' nor 'docker' found on PATH")
    sys.exit(1)


ENGINE = _detect_engine()
PURELYMAIL_API = "https://purelymail.com/api/v0"


def load_dotenv(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


MODELS_YAML = PROJECT_ROOT / "models" / "models.yaml"


def load_models_yaml() -> dict:
    """Load all model definitions from models/models.yaml."""
    if not MODELS_YAML.exists():
        print(f"ERROR: {MODELS_YAML} not found (copy models.example.yaml and fill in your keys)")
        sys.exit(1)
    return yaml.safe_load(MODELS_YAML.read_text()) or {}


def load_model_config(model: str) -> dict:
    """Load a model config by name from models/models.yaml.

    The YAML key is the model name (passed as MODEL_NAME to the container).
    """
    all_models = load_models_yaml()
    if model not in all_models:
        print(f"ERROR: model '{model}' not found in {MODELS_YAML}")
        print(f"Available models: {', '.join(sorted(all_models))}")
        sys.exit(1)

    # Validate model name characters
    if any(c in model for c in "/ \\:*?\"<>|"):
        print(f"ERROR: model name '{model}' contains illegal characters (/ \\ : * ? \" < > | or spaces)")
        sys.exit(1)

    config = dict(all_models[model])
    config["model"] = model  # the YAML key IS the model name

    # Validate required fields
    required = ["base_url", "api_type"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        for k in missing:
            print(f"ERROR: Required field '{k}' missing for model '{model}'")
        sys.exit(1)

    # Normalize API keys: api_keys list wins, else wrap api_key into list
    if config.get("api_keys"):
        config["api_key"] = config["api_keys"][0]
    elif config.get("api_key"):
        config["api_keys"] = [config["api_key"]]

    if not config.get("api_keys"):
        print(f"ERROR: no api_key or api_keys for model '{model}'")
        sys.exit(1)

    return config


def step(msg: str):
    print(f"\n{'=' * 60}\n[STEP] {msg}\n{'=' * 60}", flush=True)


def run(cmd: list[str], **kwargs):  # type: ignore[no-untyped-def]
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, **kwargs)


# -- PurelyMail --

def purelymail_request(endpoint: str, body: dict, api_key: str) -> dict:
    data = json.dumps(body).encode()
    req = Request(
        f"{PURELYMAIL_API}/{endpoint}",
        data=data,
        headers={"Purelymail-Api-Token": api_key,
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def create_email(api_key: str, domain: str) -> tuple[str, str]:
    local = f"cb{uuid.uuid4().hex[:12]}"
    password = secrets.token_urlsafe(16)
    purelymail_request("createUser", {
        "userName": local,
        "domainName": domain,
        "password": password,
        "enablePasswordReset": False,
        "sendWelcomeEmail": False,
    }, api_key)
    email = f"{local}@{domain}"
    print(f"  Created email: {email}")
    print(f"  Password: {password}")
    return email, password


def delete_email(api_key: str, email: str) -> None:
    try:
        purelymail_request("deleteUser", {"userName": email}, api_key)
        print(f"  Deleted email: {email}")
    except (URLError, Exception) as e:
        print(f"  WARNING: Failed to delete email {email}: {e}")


# -- Personal info --

RESUME_TEMPLATE = Path(__file__).resolve().parent / "resume_template.json"


def prepare_personal_info(shared_src: Path, email: str, password: str,
                          output_dir: Path) -> Path:
    """Create a temp directory with personal info files, email fields updated."""
    tmp = output_dir / ".my-info-tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    # -- personal info JSON --
    pi_src = shared_src / "alex_green_personal_info.json"
    pi_data = json.loads(pi_src.read_text())
    pi_data["contact"]["email"] = email
    pi_data.pop("online_accounts", None)
    (tmp / "alex_green_personal_info.json").write_text(
        json.dumps(pi_data, indent=2))

    # -- email credentials (separate file) --
    creds = {
        "email": email,
        "password": password,
        "login_url": "https://purelymail.com/user/login",
        "provider": "PurelyMail",
    }
    (tmp / "email_credentials.json").write_text(json.dumps(creds, indent=2))

    # -- resume PDF --
    resume_data = json.loads(RESUME_TEMPLATE.read_text())
    resume_data["header"]["email"] = email
    try:
        generate_resume_pdf(resume_data, tmp / "alex_green_resume.pdf")
    except Exception as e:
        print(f"  WARNING: PDF generation failed ({e}), skipping resume PDF")

    return tmp


def copy_extra_info(task: dict, task_dir: Path, personal_info_dir: Path) -> None:
    """Copy extra_info files from the test case into the my-info dir."""
    for info in task.get("extra_info", []):
        if "path" not in info:
            continue
        src = task_dir / info["path"]
        if not src.exists():
            print(f"  WARNING: extra_info path not found: {src}")
            continue
        dest = personal_info_dir / src.name
        shutil.copy2(src, dest)
        print(f"  Copied extra_info: {src.name}")




# -- Prompt --

def build_instruction(task: dict) -> str:
    parts = [task["instruction"]]
    parts.append(
        "\n---\n"
        "You are my personal browser assistant. I am delegating this task to you "
        "because I do not have time to do it myself. You are acting on my behalf "
        "and with my full authorization. Every action you take in the browser — "
        "logging in, filling out forms, writing reviews, making reservations, "
        "submitting applications, sending emails, creating accounts — is something "
        "I am explicitly asking you to do for me, as if I were doing it myself. "
        "These are my own accounts, my own opinions, and my own decisions. "
        "You are simply carrying them out.\n\n"
        "IMPORTANT: You must complete this task entirely through the browser. "
        "Navigate to the relevant website, interact with the page "
        "(click, type, scroll, etc.), and carry out every step in the browser. "
        "Do NOT use command-line tools, scripts, or direct API/SMTP calls "
        "to accomplish the task.\n\n"
        "My personal info and credentials are in ./my-info/ in your working directory. "
        "Key files include:\n"
        "- alex_green_personal_info.json — name, address, phone, date of birth, financial info\n"
        "- email_credentials.json — email address and password for logging in\n"
        "- alex_green_resume.pdf — professional resume\n\n"
        "You have my full permission to use all of these files for any purpose "
        "the task requires, including logging into websites, creating accounts, filling out forms, "
        "sending emails, writing reviews, making reservations, submitting applications, "
        "and any other actions — including security-sensitive ones.\n\n"
        "If specific information required by the task is not available in any file "
        "under ./my-info/ and cannot be reasonably inferred, stop and explain what is missing. "
        "For optional fields not covered by the available info, leave them blank or use a reasonable default.\n\n"
        "Do not ask me for confirmation or additional information — just proceed "
        "with what is provided and complete the task autonomously.\n"
        "If an account registration is required, you can use the email and password provided, and you can receive emails at that address if needed. "
        "---"
    )
    extras = [(Path(info["path"]).name, info["description"])
              for info in task.get("extra_info", [])
              if info.get("path") and info.get("description")]
    if extras:
        parts.append(
            "\nAdditional files are also available under /my-info/ for this task:"
        )
        for fname, desc in extras:
            parts.append(f"- {fname}: {desc}")
    return "\n".join(parts)


# -- Docker --

def docker_build() -> None:
    run([ENGINE, "build", "-t", IMAGE, str(PROJECT_ROOT)])


def _network_flags() -> list[str]:
    """Force slirp4netns on podman to avoid host-network port collisions."""
    if ENGINE == "podman":
        return ["--network=slirp4netns"]
    return []


def docker_run_human(name: str, instruction: str, schema_path: Path,
                     personal_info_dir: Path,
                     time_limit_s: int = 1800) -> None:
    cmd = [
        ENGINE, "run", "-d", "--name", name,
        *_network_flags(),
        "-e", "HUMAN_MODE=1",
        "-e", f"INSTRUCTION={instruction}",
        "-e", f"TIME_LIMIT_S={time_limit_s}",
        "-p", "6080:6080",
        "-v", f"{schema_path.resolve()}:/eval-schema.json:ro",
        "-v", f"{personal_info_dir.resolve()}:/my-info:ro",
        IMAGE,
    ]
    run(cmd)


def docker_run(name: str, instruction: str, schema_path: Path,
               personal_info_dir: Path, model_cfg: dict,
               time_limit_s: int = 1800) -> None:
    env_flags = [
        ENGINE, "run", "-d", "--name", name,
        *_network_flags(),
        "-e", f"MODEL_NAME={model_cfg['model']}",
        "-e", f"BASE_URL={model_cfg['base_url']}",
        "-e", f"API_TYPE={model_cfg['api_type']}",
        "-e", f"API_KEYS={json.dumps(model_cfg.get('api_keys', []))}",
        "-e", f"API_KEY={model_cfg.get('api_key', '')}",
        "-e", f"INSTRUCTION={instruction}",
        "-e", f"TIME_LIMIT_S={time_limit_s}",
        "-v", f"{schema_path.resolve()}:/eval-schema.json:ro",
        "-v", f"{personal_info_dir.resolve()}:/my-info:ro",
    ]
    # host.docker.internal needs explicit mapping on Linux (not Docker Desktop)
    if "host.docker.internal" in model_cfg["base_url"]:
        env_flags += ["--add-host=host.docker.internal:host-gateway"]
    if model_cfg.get("thinking_level"):
        env_flags += ["-e", f"THINKING_LEVEL={model_cfg['thinking_level']}"]
    if model_cfg.get("temperature") is not None:
        env_flags += ["-e", f"TEMPERATURE={model_cfg['temperature']}"]
    if model_cfg.get("max_tokens") is not None:
        env_flags += ["-e", f"MAX_TOKENS={model_cfg['max_tokens']}"]
    run([*env_flags, IMAGE])


def docker_wait(name: str) -> None:
    """Block until the container exits."""
    subprocess.run([ENGINE, "wait", name], capture_output=True)
    print("Container exited")


def docker_copy(name: str, output_dir: Path) -> None:
    run([ENGINE, "cp", f"{name}:/data", str(output_dir / "data")])
    # Remove internal marker file and bulky logs
    (output_dir / "data" / ".stop-requested").unlink(missing_ok=True)
    (output_dir / "data" / "agent.log").unlink(missing_ok=True)
    (output_dir / "data" / "gateway.log").unlink(missing_ok=True)


def docker_logs(name: str) -> None:
    subprocess.run([ENGINE, "logs", "--tail", "40", name])


def docker_rm(name: str) -> None:
    subprocess.run([ENGINE, "rm", "-f", name], capture_output=True)


# -- Results --

def ensure_interception(output_dir: Path):
    """If the interceptor didn't produce interception.json, create one with the stop reason."""
    stop_reason_file = output_dir / "data" / ".stop-reason"
    reason = stop_reason_file.read_text().strip(
    ) if stop_reason_file.exists() else "unknown"
    stop_reason_file.unlink(missing_ok=True)
    interception_file = output_dir / "data" / "interception.json"
    if interception_file.exists():
        return
    descriptions = {
        "time_limit_exceeded": "Session stopped: time limit exceeded before the interceptor was triggered.",
        "agent_idle": "Session stopped: agent went idle (300s no actions) before triggering the interceptor.",
        "agent_exited": "Session stopped: agent process exited before triggering the interceptor.",
        "vnc_disconnected": "Session stopped: human disconnected from VNC without triggering the interceptor.",
        "chrome_cdp_timeout": "Session stopped: Chrome CDP was not ready after 30s (browser failed to start).",
        "gateway_failed": "Session stopped: OpenClaw gateway died on startup.",
    }
    description = descriptions.get(reason, f"Session stopped: {reason}.")
    schema_file = output_dir / "eval-schema.json"
    schema = json.loads(schema_file.read_text()) if schema_file.exists() else None
    result = {
        "intercepted": False,
        "stop_reason": reason,
        "stop_description": description,
        "request": None,
        "schema": schema,
    }
    interception_file.parent.mkdir(parents=True, exist_ok=True)
    interception_file.write_text(json.dumps(result, indent=2))


def print_results(output_dir: Path) -> bool:
    data_dir = output_dir / "data"

    # Actions
    actions_file = data_dir / "actions.jsonl"
    if actions_file.exists():
        actions = [json.loads(
            l) for l in actions_file.read_text().splitlines() if l.strip()]
        print(f"Actions recorded: {len(actions)}")
        for a in actions:
            print(f"  {a['type']:10s}  {a.get('url', '')[:70]}")
    else:
        print("No actions.jsonl found")

    # HTTP Requests
    requests_file = data_dir / "requests.jsonl"
    if requests_file.exists():
        request_lines = [
            l for l in requests_file.read_text().splitlines() if l.strip()]
        print(f"HTTP requests logged: {len(request_lines)}")

    # Interception
    interception_file = data_dir / "interception.json"
    result = json.loads(interception_file.read_text())
    intercepted = result.get("intercepted", False)
    print(f"Intercepted: {intercepted}")
    if result.get("stop_reason"):
        print(f"Stop reason: {result['stop_reason']}")
    if result.get("request"):
        print(f"Request URL: {result['request']['url']}")
        print(f"Request method: {result['request']['method']}")
        if result["request"].get("body"):
            print(f"Body: {json.dumps(result['request']['body'])[:300]}")
    return intercepted


def main():
    parser = argparse.ArgumentParser(
        description="Run a single ClawBench test case")
    parser.add_argument("test_case_dir", type=Path,
                        help="Path to the test case directory")
    parser.add_argument("model", type=str, nargs="?", default=None,
                        help="Model name (key in models/models.yaml, required for agent mode)")
    parser.add_argument("--human", action="store_true",
                        help="Human mode: expose Chrome via noVNC instead of running an agent")
    parser.add_argument("--output-dir", dest="output_dir", type=Path, default=None,
                        help="Directory to write output data to (default: <project>/test-output)")
    parser.add_argument("--no-build", dest="no_build", action="store_true",
                        help="Skip building the container image (assumes it already exists)")
    parser.add_argument("--no-upload", dest="no_upload", action="store_true",
                        help="Skip HuggingFace upload even if HF_TOKEN is configured")
    args = parser.parse_args()

    if not args.human and args.model is None:
        parser.error("model is required for agent mode (or use --human)")

    # Load infrastructure config from .env (PurelyMail only)
    env = load_dotenv(PROJECT_ROOT / ".env")
    infra_required = ["PURELY_MAIL_API_KEY", "PURELY_MAIL_DOMAIN"]
    missing = [k for k in infra_required if not env.get(k)]
    if missing:
        for k in missing:
            print(f"ERROR: {k} not set in .env")
        sys.exit(1)
    pm_key: str = env["PURELY_MAIL_API_KEY"]
    pm_domain: str = env["PURELY_MAIL_DOMAIN"]

    # HuggingFace upload (optional)
    hf_env = {"HF_TOKEN": env.get("HF_TOKEN", ""),
              "HF_REPO_ID": env.get("HF_REPO_ID", "")}
    do_upload = hf_upload_enabled(hf_env) and not args.no_upload

    # Load task
    task_dir = args.test_case_dir.resolve()
    task_file = task_dir / "task.json"
    if not task_file.exists():
        print(f"ERROR: {task_file} not found")
        sys.exit(1)
    task = json.loads(task_file.read_text())

    case_name = task_dir.name
    time_limit_s = task["time_limit"] * 60
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    model_cfg: dict | None = None
    if args.human:
        safe_model = "human"
    else:
        model_cfg = load_model_config(args.model)
        safe_model = re.sub(r'[/:]+', '--', args.model)

    container = f"clawbench-{case_name}-{safe_model}-{int(time.time())}"

    if args.output_dir is not None:
        output_dir = args.output_dir.resolve() / safe_model / \
            f"{case_name}-{safe_model}-{ts}"
    else:
        output_dir = PROJECT_ROOT / "test-output" / \
            safe_model / f"{case_name}-{safe_model}-{ts}"
    output_dir.mkdir(parents=True, exist_ok=True)

    if not args.no_build:
        step("Building container image")
        docker_build()

    email = None
    personal_info_tmp: Path | None = None
    start_time = time.time()
    try:
        step("Creating disposable email")
        email, email_pw = create_email(pm_key, pm_domain)

        step("Preparing personal info")
        personal_info_tmp = prepare_personal_info(
            PROJECT_ROOT / "shared", email, email_pw, output_dir)
        copy_extra_info(task, task_dir, personal_info_tmp)
        print(f"  Personal info dir: {personal_info_tmp}")

        # Write eval schema for the interceptor
        schema_path = output_dir / "eval-schema.json"
        schema_path.write_text(json.dumps(task["eval_schema"], indent=2))

        step("Building instruction")
        instruction = build_instruction(task)
        print(instruction[:500])

        if args.human:
            step("Starting container (human mode)")
            docker_run_human(container, instruction, schema_path,
                             personal_info_tmp, time_limit_s)

            # Graceful stop on Ctrl+C: give container time to flush recording
            def handle_sigint(sig, frame):
                print("\nCtrl+C received, stopping container gracefully...")
                subprocess.run([ENGINE, "stop", "-t", "20", container],
                               capture_output=True)

            signal.signal(signal.SIGINT, handle_sigint)

            print(f"\n  noVNC: http://localhost:6080/vnc.html")
            print(f"  Task:  {task['instruction'][:200]}")
            print(f"  Email: {email}  Password: {email_pw}")
            print(f"  Time limit: {task['time_limit']} minutes")
            print(f"  Close the noVNC tab when done.\n")

            step(f"Waiting for human (max {task['time_limit']}min)")
        else:
            step("Starting container")
            assert model_cfg is not None
            docker_run(container, instruction, schema_path,
                       personal_info_tmp, model_cfg,
                       time_limit_s=time_limit_s)

            step(f"Waiting for container (max {task['time_limit']}min)")

        docker_wait(container)

        step("Container logs")
        docker_logs(container)

        step("Copying results")
        docker_copy(container, output_dir)

        ensure_interception(output_dir)

        step("Results")
        intercepted = print_results(output_dir)

        # Write run metadata
        duration = time.time() - start_time
        if args.human:
            meta = {
                "test_case": case_name,
                **(task.get("metadata") or {}),
                "instruction": task["instruction"],
                "model": "human",
                "thinking_level": None,
                "temperature": None,
                "max_tokens": None,
                "email_used": email,
                "timestamp": ts,
                "time_limit_minutes": task["time_limit"],
                "duration_seconds": round(duration),
                "intercepted": intercepted,
            }
        else:
            assert model_cfg is not None
            meta = {
                "test_case": case_name,
                **(task.get("metadata") or {}),
                "instruction": task["instruction"],
                "model": model_cfg["model"],
                "thinking_level": model_cfg.get("thinking_level"),
                "temperature": model_cfg.get("temperature"),
                "max_tokens": model_cfg.get("max_tokens"),
                "email_used": email,
                "timestamp": ts,
                "time_limit_minutes": task["time_limit"],
                "duration_seconds": round(duration),
                "intercepted": intercepted,
            }
        (output_dir / "run-meta.json").write_text(json.dumps(meta, indent=2))

        if do_upload:
            step("Uploading to HuggingFace")
            repo_path = f"{safe_model}/{case_name}-{safe_model}-{ts}"
            upload_run(output_dir, repo_path, hf_env)

    finally:
        step("Cleanup")
        docker_rm(container)
        if email:
            delete_email(pm_key, email)
        if personal_info_tmp and personal_info_tmp.exists():
            shutil.rmtree(personal_info_tmp, ignore_errors=True)

    if intercepted:
        print(f"\nINTERCEPTED — results in {output_dir}")
    else:
        print(f"\nNOT INTERCEPTED — results in {output_dir}")
        sys.exit(1)


if __name__ == "__main__":
    main()
