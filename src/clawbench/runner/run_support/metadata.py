"""Run metadata construction and serialization."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.config import (
    ASSET_ROOT,
    BASE_IMAGE,
    ENGINE,
    WORKSPACE_ROOT,
    harness_image,
)
from clawbench.runner.run_support.docker import container_engine_version, image_id
from clawbench.runner.run_support.task import normalize_extra_info

SECRET_CONFIG_RE = re.compile(
    r"(api[_-]?keys?|token|secret|password|credential)", re.IGNORECASE
)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _path_kind(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for root, kind in ((WORKSPACE_ROOT, "workspace"), (ASSET_ROOT, "bundled")):
        try:
            resolved.relative_to(root.resolve())
            return kind
        except ValueError:
            continue
    return "external"


def _display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    try:
        return str(resolved.relative_to(WORKSPACE_ROOT.resolve()))
    except ValueError:
        pass
    try:
        return f"bundled:{resolved.relative_to(ASSET_ROOT.resolve())}"
    except ValueError:
        pass
    return resolved.name


def _api_key_values(model_cfg: dict[str, Any]) -> list[str]:
    raw_keys = model_cfg.get("api_keys")
    if isinstance(raw_keys, list):
        return [str(k) for k in raw_keys if k]
    raw_key = model_cfg.get("api_key")
    return [str(raw_key)] if raw_key else []


def _sanitized_config_hash(model_cfg: dict[str, Any]) -> str:
    sanitized: dict[str, Any] = {}
    for key in sorted(model_cfg):
        value = model_cfg[key]
        if SECRET_CONFIG_RE.search(key):
            if key == "api_keys":
                sanitized[key] = f"[REDACTED:{len(_api_key_values(model_cfg))}]"
            elif value:
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value
        else:
            sanitized[key] = _json_safe(value)
    blob = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _sanitized_model_config(model_cfg: dict | None) -> dict[str, Any] | None:
    if not model_cfg:
        return None
    api_keys = _api_key_values(model_cfg)
    meta: dict[str, Any] = {
        "model": model_cfg.get("model"),
        "api_type": model_cfg.get("api_type"),
        "base_url": model_cfg.get("base_url"),
        "thinking_level": model_cfg.get("thinking_level"),
        "temperature": model_cfg.get("temperature"),
        "max_tokens": model_cfg.get("max_tokens"),
        "api_key_count": len(api_keys),
        "sanitized_config_sha256": _sanitized_config_hash(model_cfg),
    }
    extra = {
        key: _json_safe(value)
        for key, value in sorted(model_cfg.items())
        if key not in meta and not SECRET_CONFIG_RE.search(key)
    }
    if extra:
        meta["extra"] = extra
    return meta


def _runtime_meta(harness: str) -> dict[str, Any]:
    harness_ref = None if harness == "human" else harness_image(harness)
    return {
        "container_engine": ENGINE,
        "container_engine_source": (
            "env" if os.environ.get("CONTAINER_ENGINE") else "auto"
        ),
        "container_engine_version": container_engine_version(),
        "platform": sys.platform,
        "python_version": sys.version.split()[0],
        "base_image": BASE_IMAGE,
        "harness_image": harness_ref,
        "base_image_id": image_id(BASE_IMAGE),
        "harness_image_id": image_id(harness_ref) if harness_ref else None,
    }


def _task_meta(
    *,
    task: dict[str, Any],
    task_json_sha256: str | None,
    case_name: str,
    args: argparse.Namespace,
    task_dir: Path | None,
    task_file: Path | None,
) -> dict[str, Any]:
    normalized_extras, _ = normalize_extra_info(task.get("extra_info"))
    return {
        "case_name": case_name,
        "input_path": _display_path(args.test_case_dir),
        "input_path_kind": _path_kind(args.test_case_dir),
        "task_file": _display_path(task_file),
        "task_file_kind": _path_kind(task_file),
        "task_dir": _display_path(task_dir),
        "task_dir_kind": _path_kind(task_dir),
        "task_json_sha256": task_json_sha256,
        "time_limit_minutes": task.get("time_limit"),
        "has_extra_info": bool(normalized_extras),
        "extra_info_count": len(normalized_extras),
    }


def _run_flags_meta(
    *,
    args: argparse.Namespace,
    output_dir: Path | None,
    container: str | None,
    run_dir_name: str | None,
    host_port: int | None,
) -> dict[str, Any]:
    output_base = (
        args.output_dir
        if args.output_dir is not None
        else WORKSPACE_ROOT / "test-output"
    )
    return {
        "human": bool(args.human),
        "no_build": bool(args.no_build),
        "no_upload": bool(args.no_upload),
        "harness": "human" if args.human else args.harness,
        "judge": None if args.no_judge else args.judge,
        "no_judge": bool(args.no_judge),
        "output_base": _display_path(output_base),
        "output_base_kind": _path_kind(output_base),
        "output_dir": _display_path(output_dir),
        "output_dir_kind": _path_kind(output_dir),
        "run_dir_name": run_dir_name,
        "container_name": container,
        "novnc_host_port": host_port,
    }


def make_run_meta(
    *,
    task: dict | None,
    task_json_sha256: str | None,
    case_name: str,
    args: argparse.Namespace,
    model_cfg: dict | None,
    email: str | None,
    ts: str,
    duration: float,
    intercepted: bool,
    classification: dict[str, Any],
    judge_cfg: dict | None = None,
    task_dir: Path | None = None,
    task_file: Path | None = None,
    output_dir: Path | None = None,
    container: str | None = None,
    run_dir_name: str | None = None,
    host_port: int | None = None,
    personal_info_metadata: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    extra_info_warnings: list[str] | None = None,
) -> dict[str, Any]:
    task = task if isinstance(task, dict) else {}
    raw_metadata = task.get("metadata")
    metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
    if args.human:
        model = "human"
        harness = "human"
        thinking_level = temperature = max_tokens = None
    else:
        model = model_cfg["model"] if model_cfg else args.model
        harness = args.harness
        thinking_level = model_cfg.get("thinking_level") if model_cfg else None
        temperature = model_cfg.get("temperature") if model_cfg else None
        max_tokens = model_cfg.get("max_tokens") if model_cfg else None

    meta = {
        "test_case": case_name,
        **metadata,
        "task_json_sha256": task_json_sha256,
        "instruction": task.get("instruction"),
        "model": model,
        "harness": harness,
        "thinking_level": thinking_level,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "email_used": email,
        "timestamp": ts,
        "time_limit_minutes": task.get("time_limit"),
        "duration_seconds": round(duration),
        "intercepted": intercepted,
        "result_category": classification["result_category"],
        "failure_category": classification["failure_category"],
        "infra_failure": classification["infra_failure"],
        "adjusted_eligible": classification["adjusted_eligible"],
        "infra_flags": classification["infra_flags"],
        "run_metrics": classification["metrics"],
        "usage": classification["metrics"].get("usage"),
        "runtime": _runtime_meta(harness),
        "task": _task_meta(
            task=task,
            task_json_sha256=task_json_sha256,
            case_name=case_name,
            args=args,
            task_dir=task_dir,
            task_file=task_file,
        ),
        "model_config": _sanitized_model_config(model_cfg),
        "run_flags": _run_flags_meta(
            args=args,
            output_dir=output_dir,
            container=container,
            run_dir_name=run_dir_name,
            host_port=host_port,
        ),
    }
    sanitized_judge_cfg = _sanitized_model_config(judge_cfg)
    if sanitized_judge_cfg is not None:
        meta["judge_config"] = sanitized_judge_cfg
    if personal_info_metadata is not None:
        meta["personal_info"] = personal_info_metadata
    if failure_reason:
        meta["failure_reason"] = failure_reason
    if extra_info_warnings:
        meta["extra_info_warnings"] = extra_info_warnings
    return meta


def write_run_meta(output_dir: Path, meta: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run-meta.json").write_text(json.dumps(meta, indent=2))
