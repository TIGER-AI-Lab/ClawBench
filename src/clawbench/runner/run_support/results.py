"""Result collection and classification helpers."""

import json
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.usage import (
    format_usage_summary,
    summarize_usage_file,
)

INFRA_STOP_REASONS = {
    "chrome_cdp_timeout",
    "gateway_failed",
    "opencode_failed",
    "claude_code_failed",
    "codex_failed",
    "browser_use_failed",
    "hermes_failed",
    "pi_failed",
    "proxy_failed",
    "missing_harness",
    # Harbor harness infra failures (clawbench.runtime.harnesses.harbor): the
    # agent-browser CDP bridge could not attach (run-harbor.sh:41), or the Terminus
    # driver died on startup / crashed (run-harbor.sh:55, harbor_driver.py:368).
    # Without these, a Harbor infra failure was misclassified as an agent failure.
    "agent_browser_cdp_failed",
    "harbor_failed",
}

API_OR_CREDIT_PATTERNS = (
    "insufficient credit",
    "insufficient balance",
    "out of credits",
    "credit balance",
    "quota exceeded",
    "rate limit",
    "ratelimit",
    "too many requests",
    "payment required",
    "billing error",
    "billing issue",
    "invalid api key",
    "api key is invalid",
    "unauthorized",
    "forbidden",
    "authentication failed",
    "authentication error",
    "status code 401",
    "status code 402",
    "status code 403",
    "status code 429",
    "http 401",
    "http 402",
    "http 403",
    "http 429",
    "api call failed",
    "provider returned error",
    " 401 ",
    " 402 ",
    " 403 ",
    " 429 ",
)

NON_MODEL_FAILURE_CATEGORIES = {
    "infra_failure",
    "api_or_credit",
    "task_data",
    "build_instruction",
}


def _count_jsonl(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    try:
        with path.open(errors="replace") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _line_has_api_or_credit_evidence(line: str) -> bool:
    lowered = f" {line.lower()} "
    return any(pattern in lowered for pattern in API_OR_CREDIT_PATTERNS)


def collect_run_metrics(
    output_dir: Path,
    model_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data_dir = output_dir / "data"
    actions_file = data_dir / "actions.jsonl"
    requests_file = data_dir / "requests.jsonl"
    messages_file = data_dir / "agent-messages.jsonl"
    usage_file = data_dir / "usage.jsonl"
    screenshots_dir = data_dir / "screenshots"
    recording_file = data_dir / "recording.mp4"
    interception_file = data_dir / "interception.json"

    metrics: dict[str, Any] = {
        "actions": _count_jsonl(actions_file),
        "requests": _count_jsonl(requests_file),
        "messages": _count_jsonl(messages_file),
        "screenshots": (
            sum(1 for _ in screenshots_dir.iterdir()) if screenshots_dir.is_dir() else 0
        ),
        "recording_bytes": (
            recording_file.stat().st_size if recording_file.exists() else 0
        ),
        "api_calls": 0,
        "stop_reason": None,
        "missing_files": [],
        "api_or_credit_evidence": None,
    }

    for rel in (
        "data/actions.jsonl",
        "data/requests.jsonl",
        "data/agent-messages.jsonl",
        "data/interception.json",
        "data/recording.mp4",
    ):
        if not (output_dir / rel).exists():
            metrics["missing_files"].append(rel)

    interception = _read_json(interception_file)
    if isinstance(interception, dict):
        metrics["stop_reason"] = interception.get("stop_reason")

    explicit_api_calls: int | None = None
    derived_api_call_keys: set[str] = set()
    derived_api_start_keys: set[tuple[str, str, str]] = set()
    derived_api_response_start_keys: set[tuple[str, str, str]] = set()
    browser_use_model_outputs = 0
    if messages_file.exists():
        try:
            with messages_file.open(errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    if isinstance(event.get("model_output"), dict):
                        browser_use_model_outputs += 1
                    if event.get("type") == "session_meta" and isinstance(
                        event.get("api_call_count"), int
                    ):
                        explicit_api_calls = event["api_call_count"]
                    msg = event.get("message")
                    if isinstance(msg, dict):
                        role = msg.get("role")
                        if role == "assistant" and (
                            msg.get("api") or msg.get("provider") or msg.get("usage")
                        ):
                            provider = str(msg.get("provider") or "")
                            model = str(msg.get("model") or "")
                            timestamp = str(msg.get("timestamp") or "")
                            response_id = msg.get("responseId")
                            if response_id:
                                key = "|".join([provider, model, str(response_id)])
                                if timestamp:
                                    derived_api_response_start_keys.add(
                                        (provider, model, timestamp)
                                    )
                            elif (
                                event.get("type") == "message_start"
                                and not msg.get("content")
                                and timestamp
                            ):
                                key = ""
                                derived_api_start_keys.add((provider, model, timestamp))
                            else:
                                key = "|".join(
                                    [
                                        provider,
                                        model,
                                        timestamp,
                                        str(event.get("id") or ""),
                                    ]
                                )
                            if key:
                                derived_api_call_keys.add(key)
                        err = msg.get("errorMessage") or msg.get("error")
                        if (
                            err
                            and metrics["api_or_credit_evidence"] is None
                            and _line_has_api_or_credit_evidence(str(err))
                        ):
                            metrics["api_or_credit_evidence"] = str(err)[:500]
        except OSError:
            pass

    if explicit_api_calls is not None:
        metrics["api_calls"] = explicit_api_calls
    elif derived_api_call_keys or derived_api_start_keys:
        for key in derived_api_start_keys - derived_api_response_start_keys:
            derived_api_call_keys.add("message_start|" + "|".join(key))
        metrics["api_calls"] = len(derived_api_call_keys)
    elif browser_use_model_outputs:
        metrics["api_calls"] = browser_use_model_outputs

    usage = summarize_usage_file(usage_file, model_cfg=model_cfg)
    if usage["api_calls"] > metrics["api_calls"]:
        metrics["api_calls"] = usage["api_calls"]
    metrics["usage"] = usage

    if metrics["api_or_credit_evidence"] is None and data_dir.exists():
        for log_file in data_dir.glob("*.log"):
            try:
                with log_file.open(errors="replace") as f:
                    for line in f:
                        if _line_has_api_or_credit_evidence(line):
                            metrics["api_or_credit_evidence"] = (
                                f"{log_file.name}: {line.strip()[:450]}"
                            )
                            break
            except OSError:
                continue
            if metrics["api_or_credit_evidence"] is not None:
                break

    return metrics


def classify_run(
    output_dir: Path,
    intercepted: bool,
    default_failure_category: str | None = None,
    model_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = collect_run_metrics(output_dir, model_cfg=model_cfg)
    infra_flags: list[str] = []
    if metrics["api_calls"] == 0:
        infra_flags.append("zero_api_calls")
    if metrics["actions"] == 0:
        infra_flags.append("zero_actions")
    if metrics["requests"] == 0:
        infra_flags.append("zero_requests")
    if metrics["messages"] == 0:
        infra_flags.append("zero_agent_messages")
    if metrics["recording_bytes"] == 0:
        infra_flags.append("missing_or_empty_recording")
    for rel in metrics["missing_files"]:
        infra_flags.append(f"missing:{rel}")

    if intercepted:
        category = None
        result_category = "intercepted"
    elif default_failure_category:
        category = default_failure_category
        result_category = default_failure_category
    elif metrics["api_or_credit_evidence"]:
        category = "api_or_credit"
        result_category = category
    elif metrics["stop_reason"] in INFRA_STOP_REASONS:
        category = "infra_failure"
        result_category = category
    elif (
        metrics["api_calls"] == 0
        and metrics["actions"] == 0
        and metrics["requests"] == 0
    ):
        category = "infra_failure"
        result_category = category
    elif metrics["messages"] == 0 or not (output_dir / "data").exists():
        category = "infra_failure"
        result_category = category
    else:
        category = "model_not_intercepted"
        result_category = category

    adjusted_eligible = category not in NON_MODEL_FAILURE_CATEGORIES
    return {
        "result_category": result_category,
        "failure_category": category,
        "infra_failure": category == "infra_failure",
        "adjusted_eligible": adjusted_eligible,
        "infra_flags": infra_flags,
        "metrics": metrics,
    }


def ensure_interception(output_dir: Path):
    """If the interceptor didn't produce interception.json, create one with the stop reason."""
    stop_reason_file = output_dir / "data" / ".stop-reason"
    reason = (
        stop_reason_file.read_text().strip() if stop_reason_file.exists() else "unknown"
    )
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
        "opencode_failed": "Session stopped: opencode process died on startup.",
        "claude_code_failed": "Session stopped: Claude Code process died on startup.",
        "codex_failed": "Session stopped: Codex CLI process died on startup.",
        "browser_use_failed": "Session stopped: browser-use process died on startup.",
        "hermes_failed": "Session stopped: Hermes Agent process died on startup.",
        "pi_failed": "Session stopped: Pi coding agent process died on startup.",
        "proxy_failed": "Session stopped: LiteLLM API translation proxy failed to start.",
        "missing_harness": "Session stopped: container image was built without a harness layer.",
        "agent_browser_cdp_failed": "Session stopped: the agent-browser CLI could not attach to Chrome over CDP (Harbor browser bridge failed).",
        "harbor_failed": "Session stopped: the Harbor agent (Terminus 2) process died on startup or crashed.",
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


def print_results(
    output_dir: Path,
    model_cfg: dict[str, Any] | None = None,
) -> bool:
    data_dir = output_dir / "data"

    actions_file = data_dir / "actions.jsonl"
    if actions_file.exists():
        actions = [
            json.loads(line)
            for line in actions_file.read_text().splitlines()
            if line.strip()
        ]
        print(f"Actions recorded: {len(actions)}")
        for a in actions:
            print(f"  {a['type']:10s}  {a.get('url', '')[:70]}")
    else:
        print("No actions.jsonl found")

    requests_file = data_dir / "requests.jsonl"
    if requests_file.exists():
        request_lines = [
            line for line in requests_file.read_text().splitlines() if line.strip()
        ]
        print(f"HTTP requests logged: {len(request_lines)}")

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
    usage = summarize_usage_file(data_dir / "usage.jsonl", model_cfg=model_cfg)
    print(format_usage_summary(usage))
    return intercepted


def remove_transient_usage_artifact(output_dir: Path) -> None:
    """Remove the harness handoff artifact after run-meta.json has usage."""
    (output_dir / "data" / "usage.jsonl").unlink(missing_ok=True)
