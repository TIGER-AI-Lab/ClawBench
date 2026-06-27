"""Task data, prompt, and personal-info helpers."""

import hashlib
import json
import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.resume import generate_resume_pdf

RESUME_TEMPLATE = Path(__file__).resolve().parent / "resume_template.json"

# Built-in persona files build_instruction() advertises under /my-info/, as
# (filename, description) pairs. Single source of truth so the Harbor exporter can
# stage and validate exactly the files the prompt references (clawbench.harbor.export).
BUILTIN_MY_INFO_FILES: tuple[tuple[str, str], ...] = (
    (
        "alex_green_personal_info.json",
        "name, address, phone, date of birth, financial info",
    ),
    ("email_credentials.json", "email address and password for logging in"),
    ("alex_green_resume.pdf", "professional resume"),
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_personal_info(
    shared_src: Path, email: str, password: str, output_dir: Path
) -> tuple[Path, dict[str, str]]:
    """Create a temp directory with personal info files, email fields updated."""
    tmp = output_dir / ".my-info-tmp"
    tmp.mkdir(parents=True, exist_ok=True)

    pi_src = shared_src / "alex_green_personal_info.json"
    pi_source_bytes = pi_src.read_bytes()
    pi_data = json.loads(pi_source_bytes)
    pi_data["contact"]["email"] = email
    pi_data.pop("online_accounts", None)
    personal_info_json = json.dumps(pi_data, indent=2)
    (tmp / "alex_green_personal_info.json").write_text(personal_info_json)

    creds = {
        "email": email,
        "password": password,
        "login_url": "https://purelymail.com/user/login",
        "provider": "PurelyMail",
    }
    (tmp / "email_credentials.json").write_text(json.dumps(creds, indent=2))

    resume_template_bytes = RESUME_TEMPLATE.read_bytes()
    resume_data = json.loads(resume_template_bytes)
    resume_data["header"]["email"] = email
    resume_source_json = json.dumps(resume_data, indent=2)
    try:
        generate_resume_pdf(resume_data, tmp / "alex_green_resume.pdf")
    except Exception as e:
        print(f"  WARNING: PDF generation failed ({e}), skipping resume PDF")

    metadata = {
        "personal_info_source_json_sha256": _sha256_bytes(pi_source_bytes),
        "personal_info_json_sha256": _sha256_bytes(personal_info_json.encode()),
        "resume_template_json_sha256": _sha256_bytes(resume_template_bytes),
        "resume_pdf_source_json_sha256": _sha256_bytes(resume_source_json.encode()),
    }
    return tmp, metadata


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=True)
    except TypeError:
        return str(value)


def normalize_extra_info(raw: Any) -> tuple[list[dict[str, str]], list[str]]:
    """Normalize legacy and schema-compliant extra_info shapes."""
    entries: list[dict[str, str]] = []
    warnings: list[str] = []

    def add_item(item: Any, label: str) -> None:
        if item is None:
            return
        if isinstance(item, str):
            note = item.strip()
            if note:
                entries.append({"description": note})
            return
        if isinstance(item, (int, float, bool)):
            entries.append({"description": str(item)})
            return
        if not isinstance(item, dict):
            warnings.append(
                f"{label} has unsupported type {type(item).__name__}; ignoring"
            )
            return

        path = ""
        raw_path = item.get("path")
        if raw_path not in (None, ""):
            if isinstance(raw_path, (str, os.PathLike)):
                path = str(raw_path)
            else:
                warnings.append(
                    f"{label}.path has unsupported type "
                    f"{type(raw_path).__name__}; ignoring path"
                )

        raw_desc = None
        for key in ("description", "note", "content", "text", "message", "value"):
            if item.get(key) not in (None, ""):
                raw_desc = item.get(key)
                break
        description = _text_value(raw_desc)

        if path or description:
            entry: dict[str, str] = {}
            if path:
                entry["path"] = path
            entry["description"] = description or "Additional task file"
            entries.append(entry)
            return

        if item:
            entries.append({"description": _text_value(item)})

    if raw in (None, ""):
        return entries, warnings
    if isinstance(raw, list):
        for idx, item in enumerate(raw):
            add_item(item, f"extra_info[{idx}]")
    else:
        add_item(raw, "extra_info")
    return entries, warnings


def copy_extra_info(task: dict, task_dir: Path, personal_info_dir: Path) -> list[str]:
    """Copy extra_info files from the test case into the my-info dir."""
    entries, warnings = normalize_extra_info(task.get("extra_info"))
    for warning in warnings:
        print(f"  WARNING: {warning}")
    for info in entries:
        rel_path = info.get("path")
        if not rel_path:
            continue
        src = task_dir / rel_path
        if not src.exists():
            warning = f"extra_info path not found: {src}"
            warnings.append(warning)
            print(f"  WARNING: {warning}")
            continue
        if not src.is_file():
            warning = f"extra_info path is not a file: {src}"
            warnings.append(warning)
            print(f"  WARNING: {warning}")
            continue
        dest = personal_info_dir / src.name
        try:
            shutil.copy2(src, dest)
        except OSError as e:
            warning = f"failed to copy extra_info {src}: {e}"
            warnings.append(warning)
            print(f"  WARNING: {warning}")
            continue
        print(f"  Copied extra_info: {src.name}")
    return warnings


def build_instruction(
    task: dict, *, builtin_files: Sequence[tuple[str, str]] | None = None
) -> str:
    instruction = task.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("task instruction must be a non-empty string")

    # Advertise only the built-in my-info files actually available. Defaults to the
    # full bundle (native runner); the Harbor exporter passes the subset it staged
    # so the prompt never references a file that is missing from /my-info/.
    files = BUILTIN_MY_INFO_FILES if builtin_files is None else tuple(builtin_files)
    persona = (
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
    )
    if files:
        persona += "Key files include:\n" + "".join(
            f"- {name} — {desc}\n" for name, desc in files
        )
    persona += (
        "\n"
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
    parts = [instruction, persona]
    normalized_extras, _ = normalize_extra_info(task.get("extra_info"))
    file_extras = [
        (Path(info["path"]).name, info["description"])
        for info in normalized_extras
        if info.get("path")
    ]
    notes = [info["description"] for info in normalized_extras if not info.get("path")]
    if file_extras:
        parts.append(
            "\nAdditional files are also available under /my-info/ for this task:"
        )
        for fname, desc in file_extras:
            parts.append(f"- {fname}: {desc}")
    if notes:
        parts.append("\nAdditional task notes:")
        for note in notes:
            parts.append(f"- {note}")
    return "\n".join(parts)


def validate_task_data(task: Any, task_file: Path) -> dict:
    if not isinstance(task, dict):
        raise ValueError(f"{task_file} must contain a JSON object")
    instruction = task.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("task instruction must be a non-empty string")
    eval_schema = task.get("eval_schema")
    if not isinstance(eval_schema, dict):
        raise ValueError("task eval_schema must be an object")
    if not isinstance(eval_schema.get("url_pattern"), str):
        raise ValueError("task eval_schema.url_pattern must be a string")
    if not isinstance(eval_schema.get("method"), str):
        raise ValueError("task eval_schema.method must be a string")
    raw_time_limit = task.get("time_limit")
    if not isinstance(raw_time_limit, int | float) or isinstance(raw_time_limit, bool):
        raise ValueError("task time_limit must be a number") from None
    time_limit = float(raw_time_limit)
    if time_limit <= 0:
        raise ValueError("task time_limit must be greater than 0")
    return task
