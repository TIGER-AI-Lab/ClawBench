#!/usr/bin/env python3
"""Kernel browser lifecycle for the ClawBench Harbor control arm.

Mirrors the native runner's browser-runtime phases (start / finalize /
cleanup) inside a Harbor task container, reusing the same provider
implementation the native runner uses. The Kernel API key and the real
provider CDP URL stay in root-only files under /tmp/clawbench-run; the
benchmark agent only ever sees the credential-free CDP bridge exposed by
the ClawBench runtime server.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:  # Vendored next to this script inside Harbor task environments.
    from browser_runtime_providers import (  # type: ignore[import-not-found]
        BrowserRuntimeError,
        BrowserSession,
        KernelRuntimeProvider,
        redact_cdp_url,
    )
except ImportError:  # Source checkout / tests.
    from clawbench.runner.run_support.browser_runtime.providers import (
        BrowserRuntimeError,
        BrowserSession,
        KernelRuntimeProvider,
        redact_cdp_url,
    )

DATA_DIR = Path(os.environ.get("CLAWBENCH_DATA_DIR", "/data"))
STATE_DIR = Path("/tmp/clawbench-run")
STATE_FILE = STATE_DIR / "kernel-browser-state.json"
CDP_URL_FILE = STATE_DIR / "kernel-cdp-url"
METADATA_FILE = (
    Path(os.environ.get("CLAWBENCH_MY_INFO_DIR", "/my-info")) / "kernel_browser.json"
)
LIFECYCLE_FILE = DATA_DIR / "kernel-browser-lifecycle.json"
TASK_FILE = Path("/task.json")
RUNTIME_SERVER_BRIDGE_URL = "http://127.0.0.1:7878"


def _load_provider() -> KernelRuntimeProvider:
    api_key = os.environ.get("KERNEL_API_KEY", "")
    if not api_key:
        raise SystemExit("KERNEL_API_KEY is required for the kernel browser runtime")
    options: dict[str, Any] = {}
    raw_options = os.environ.get("CLAWBENCH_BROWSER_RUNTIME_OPTIONS", "")
    if raw_options:
        options = json.loads(raw_options)
        if not isinstance(options, dict):
            raise SystemExit("CLAWBENCH_BROWSER_RUNTIME_OPTIONS must be a JSON object")
    return KernelRuntimeProvider(
        api_key=api_key,
        options=options,
        api_url=os.environ.get("KERNEL_BASE_URL") or "https://api.onkernel.com",
    )


def _load_state() -> dict[str, Any] | None:
    if STATE_FILE.is_file():
        return json.loads(STATE_FILE.read_text())
    # Fall back to the agent-visible metadata so cleanup still works if the
    # state file was lost but the browser was created.
    if METADATA_FILE.is_file():
        metadata = json.loads(METADATA_FILE.read_text())
        if metadata.get("session_id"):
            return {"metadata": metadata, "events": []}
    return None


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
    STATE_FILE.chmod(0o600)
    if state.get("cdp_url"):
        CDP_URL_FILE.write_text(str(state["cdp_url"]))
        CDP_URL_FILE.chmod(0o600)


def _public_metadata(state: dict[str, Any]) -> dict[str, Any]:
    """Credential-free view of the session for the agent-visible file."""
    metadata = state.get("metadata", {})
    inner = (
        metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    )
    return {
        "provider": "kernel",
        "mode": "remote",
        "runtime": "kernel",
        "session_id": metadata.get("session_id"),
        "replay_id": inner.get("replay_id") or metadata.get("replay_id"),
        "region": inner.get("region") or metadata.get("region"),
        "stealth": (
            inner["stealth"] if "stealth" in inner else metadata.get("stealth")
        ),
        "timeout_seconds": (
            inner.get("timeout_seconds") or metadata.get("timeout_seconds")
        ),
        "cdp_url": redact_cdp_url(metadata["cdp_url"])
        if metadata.get("cdp_url")
        else None,
        "viewer_url": "[REDACTED]" if metadata.get("viewer_url") else None,
        "cdp_bridge_url": RUNTIME_SERVER_BRIDGE_URL,
        "recording_mode": "provider-download",
        "status": state.get("status"),
        "cleanup_status": state.get("cleanup_status"),
        "cleanup_error": state.get("cleanup_error"),
        "deletion_verified": state.get("deletion_verified"),
        "events": state.get("events", []),
    }


def _write_metadata(state: dict[str, Any]) -> None:
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    METADATA_FILE.write_text(json.dumps(_public_metadata(state), indent=2))


def _record(state: dict[str, Any], event: str, **fields: Any) -> None:
    entry = {"event": event, "ts": time.time(), **fields}
    state.setdefault("events", []).append(entry)
    print(json.dumps(entry), flush=True)


def _task_time_limit_s() -> int:
    task = json.loads(TASK_FILE.read_text())
    return int(float(task["time_limit"]) * 60)


def cmd_start() -> int:
    if STATE_FILE.is_file():
        state = json.loads(STATE_FILE.read_text())
        if state.get("status") == "created":
            print("Kernel browser already created for this trial", flush=True)
            _write_metadata(state)
            return 0

    provider = _load_provider()
    task = json.loads(TASK_FILE.read_text())
    session = provider.start(task, _task_time_limit_s())
    state: dict[str, Any] = {
        "status": "created",
        "cdp_url": session.cdp_url,
        "metadata": session.to_metadata(),
        "events": [],
    }
    # to_metadata redacts the CDP URL; keep the real one for the runtime
    # server only, in the 0600 state file.
    state["metadata"]["cdp_url"] = session.cdp_url
    _record(state, "browser_created", session_id=session.session_id)
    _save_state(state)
    _write_metadata(state)
    print(
        f"Kernel browser ready; CDP bridge at {RUNTIME_SERVER_BRIDGE_URL}", flush=True
    )
    return 0


def _download_recording(provider: KernelRuntimeProvider, state: dict[str, Any]) -> None:
    staging = STATE_DIR / "finalize-output"
    shutil.rmtree(staging, ignore_errors=True)
    session = _session_from_state(state)
    provider.finalize(session, staging)
    recording = staging / "data" / "recording.mp4"
    if recording.is_file():
        dest = DATA_DIR / "recording.mp4"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(recording), dest)
        state["recording_bytes"] = dest.stat().st_size


def _session_from_state(state: dict[str, Any]) -> BrowserSession:
    metadata = state.get("metadata", {})
    inner = (
        metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    )
    return BrowserSession(
        provider="kernel",
        mode="remote",
        session_id=metadata.get("session_id"),
        cdp_url=metadata.get("cdp_url", ""),
        metadata={
            "replay_id": inner.get("replay_id") or metadata.get("replay_id"),
        },
        recording_mode="provider-download",
    )


def cmd_finalize() -> int:
    state = _load_state()
    if state is None:
        print("No Kernel browser was created; nothing to finalize", flush=True)
        return 0
    if state.get("status") == "deleted":
        print("Kernel browser already finalized and deleted", flush=True)
        return 0

    provider = _load_provider()
    session_id = state.get("metadata", {}).get("session_id")
    try:
        _download_recording(provider, state)
        _record(state, "replay_finalized", recording_bytes=state.get("recording_bytes"))
        state["status"] = "finalized"
        _write_metadata(state)
    except BrowserRuntimeError as e:
        # The replay is lost, but deletion must still proceed.
        state["cleanup_error"] = f"replay finalization failed: {e}"
        _record(state, "replay_finalization_failed", error=str(e))

    try:
        provider.cleanup(_session_from_state(state))
        state["cleanup_status"] = "deleted"
    except BrowserRuntimeError as e:
        state["cleanup_error"] = str(e)
        _record(state, "finalize_failed", error=str(e))
        _save_state(state)
        _write_metadata(state)
        return 1

    _verify_deletion(provider, state)
    state["status"] = "deleted"
    _record(
        state,
        "browser_deleted",
        session_id=session_id,
        cleanup_status=state.get("cleanup_status"),
        deletion_verified=state.get("deletion_verified"),
    )
    _save_state(state)
    _write_metadata(state)
    _write_lifecycle(state)
    return 0


def cmd_cleanup() -> int:
    """Cleanup-only path (e.g. setup failed after the browser was created)."""
    state = _load_state()
    if state is None or state.get("status") == "deleted":
        print("No Kernel browser to clean up", flush=True)
        return 0

    provider = _load_provider()
    try:
        provider.cleanup(_session_from_state(state))
        state["cleanup_status"] = "deleted"
    except BrowserRuntimeError as e:
        state["cleanup_error"] = str(e)
        _record(state, "cleanup_failed", error=str(e))
        _write_metadata(state)
        return 1

    _verify_deletion(provider, state)
    state["status"] = "deleted"
    _record(state, "browser_deleted", cleanup_status=state.get("cleanup_status"))
    _save_state(state)
    _write_metadata(state)
    _write_lifecycle(state)
    return 0


def _verify_deletion(provider: KernelRuntimeProvider, state: dict[str, Any]) -> None:
    session_id = state.get("metadata", {}).get("session_id")
    if not session_id:
        state["deletion_verified"] = False
        return
    try:
        state["deletion_verified"] = not provider.session_exists(session_id)
    except BrowserRuntimeError as e:
        state["deletion_verified"] = False
        state["cleanup_error"] = f"deletion check failed: {e}"


def _write_lifecycle(state: dict[str, Any]) -> None:
    LIFECYCLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIFECYCLE_FILE.write_text(json.dumps(_public_metadata(state), indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "finalize", "cleanup"])
    args = parser.parse_args()
    return {"start": cmd_start, "finalize": cmd_finalize, "cleanup": cmd_cleanup}[
        args.command
    ]()


if __name__ == "__main__":
    raise SystemExit(main())
