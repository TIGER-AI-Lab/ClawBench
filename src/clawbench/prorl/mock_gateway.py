"""Offline mock of the Polar Rollout Server + ``harbor`` evaluator.

Lets us verify the full ClawBench submit -> episode -> two-stage-reward -> trace
handshake **without GPUs, an inference server, or a browser** — a contract test,
not a real rollout. It faithfully mirrors two things:

* the Rollout Server HTTP surface (``POST /rollout/task/submit`` returning a
  ``task_id``; ``GET /rollout/task/{id}`` returning a completed ``TaskStatus``
  with ``sessions[].trajectory.traces[-1].reward``), and
* Polar's ``harbor`` evaluator reward rule: run ``test_command``, then read
  ``reward.txt`` (float) else ``reward.json`` (scalar or ``{name: reward}``
  averaged), clamped to ``[0, 1]``.

Because it runs offline, it relocates the container-absolute ``/tests`` and
``/logs/verifier`` paths into a temp sandbox and exports ``VERIFIER_DIR`` so a
stub ``test.sh`` can write its reward there. The real gateway uses the true
container paths.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def run_harbor_evaluator(
    tests_dir: str | Path,
    *,
    test_command: str = "bash /tests/test.sh",
    verifier_timeout: int = 180,
) -> tuple[float, dict[str, Any]]:
    """Offline mirror of Polar's ``harbor`` evaluator; returns (reward, meta)."""
    sandbox = Path(tempfile.mkdtemp(prefix="clawbench-mock-eval-"))
    try:
        tests_target = sandbox / "tests"
        verifier_dir = sandbox / "logs" / "verifier"
        verifier_dir.mkdir(parents=True, exist_ok=True)
        shutil.copytree(tests_dir, tests_target)

        # Relocate the container-absolute paths for offline execution.
        cmd = test_command.replace("/tests", str(tests_target)).replace(
            "/logs/verifier", str(verifier_dir)
        )
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(sandbox),
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "VERIFIER_DIR": str(verifier_dir),
                "TESTS_DIR": str(tests_target),
            },
            capture_output=True,
            text=True,
            timeout=verifier_timeout,
        )

        reward = _read_reward(verifier_dir)
        return reward, {
            "verifier_exit_code": proc.returncode,
            "stdout_tail": proc.stdout[-500:],
            "stderr_tail": proc.stderr[-500:],
        }
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)


def _read_reward(verifier_dir: Path) -> float:
    """reward.txt (float) first, then reward.json (scalar or dict-averaged)."""
    txt = verifier_dir / "reward.txt"
    if txt.is_file():
        try:
            return _clamp01(float(txt.read_text().strip()))
        except ValueError:
            pass
    js = verifier_dir / "reward.json"
    if js.is_file():
        data = json.loads(js.read_text())
        if isinstance(data, (int, float)):
            return _clamp01(float(data))
        if isinstance(data, dict):
            vals = [float(v) for v in data.values() if isinstance(v, (int, float))]
            if vals:
                return _clamp01(sum(vals) / len(vals))
    return 0.0


class _MockState:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def submit(self, payload: dict[str, Any]) -> str:
        with self._lock:
            self._counter += 1
            task_id = f"mock-task-{self._counter:04d}"
        cfg = (payload.get("evaluator") or {}).get("config") or {}
        tests_dir = cfg.get("tests_dir")
        if not tests_dir:
            raise ValueError("evaluator.config.tests_dir is required")
        test_command = cfg.get("test_command", "bash /tests/test.sh")
        n = int(payload.get("num_samples", 1))
        sessions = []
        for i in range(n):
            reward, meta = run_harbor_evaluator(tests_dir, test_command=test_command)
            sessions.append(
                {
                    "session_id": f"{task_id}-ses-{i:02d}",
                    "trajectory": {
                        "status": "COMPLETED",
                        "traces": [{"reward": reward}],
                    },
                    "eval_metadata": meta,
                }
            )
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": "completed",
            "sessions": sessions,
        }
        return task_id


def _make_handler(state: _MockState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 (base sig)
            pass  # silence request logging

        def _send(self, code: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") != "/rollout/task/submit":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode() or "{}")
            try:
                task_id = state.submit(payload)
            except Exception as e:  # surface eval errors as a 500 body
                self._send(500, {"error": str(e)})
                return
            self._send(200, {"task_id": task_id})

        def do_GET(self) -> None:  # noqa: N802
            parts = self.path.rstrip("/").split("/")
            if len(parts) >= 4 and parts[1] == "rollout" and parts[2] == "task":
                task = state.tasks.get(parts[3])
                self._send(200 if task else 404, task or {"error": "unknown task"})
                return
            self._send(404, {"error": "not found"})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8080) -> ThreadingHTTPServer:
    """Start the mock server (call ``.shutdown()`` to stop)."""
    server = ThreadingHTTPServer((host, port), _make_handler(_MockState()))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Offline mock Polar Rollout Server for ClawBench"
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args(argv)
    server = serve(args.host, args.port)
    print(
        f"mock Polar rollout server on http://{args.host}:{args.port} (Ctrl-C to stop)"
    )
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
