"""End-to-end contract test via the offline mock Polar rollout server."""

from __future__ import annotations

from pathlib import Path

from clawbench.prorl import mock_gateway, submit


def _stub_tests_dir(tmp_path: Path, reward: float) -> Path:
    """A tests/ dir whose test.sh writes a fixed reward (no browser/runtime)."""
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test.sh").write_text(
        "#!/bin/bash\n"
        "set -e\n"
        'mkdir -p "$VERIFIER_DIR"\n'
        f'echo \'{{"reward": {reward}}}\' > "$VERIFIER_DIR/reward.json"\n'
    )
    return tests


def test_harbor_evaluator_reads_reward(tmp_path: Path) -> None:
    tests = _stub_tests_dir(tmp_path, 1.0)
    reward, meta = mock_gateway.run_harbor_evaluator(tests)
    assert reward == 1.0
    assert meta["verifier_exit_code"] == 0


def test_harbor_evaluator_clamps_and_defaults(tmp_path: Path) -> None:
    tests = _stub_tests_dir(tmp_path, 5.0)  # out of range -> clamped
    reward, _ = mock_gateway.run_harbor_evaluator(tests)
    assert reward == 1.0

    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "test.sh").write_text("#!/bin/bash\ntrue\n")  # writes no reward
    reward2, _ = mock_gateway.run_harbor_evaluator(empty)
    assert reward2 == 0.0


def test_full_submit_poll_reward_over_http(tmp_path: Path) -> None:
    """Hand-built payload → mock server → client submit/poll/extract reward."""
    tests = _stub_tests_dir(tmp_path, 0.75)
    payload = {
        "task_id": "v2-smoke",
        "num_samples": 3,
        "evaluator": {
            "strategy": "harbor",
            "config": {"tests_dir": str(tests), "test_command": "bash /tests/test.sh"},
        },
    }

    server = mock_gateway.serve(host="127.0.0.1", port=0)
    try:
        host, port = server.server_address[0], server.server_address[1]
        url = f"http://{host}:{port}"
        task_id = submit.submit_task(url, payload)
        status = submit.poll_task(url, task_id, interval=0.05, max_wait=30)
        rewards = submit.extract_rewards(status)
    finally:
        server.shutdown()

    assert status["status"] == "completed"
    assert rewards == [0.75, 0.75, 0.75]
