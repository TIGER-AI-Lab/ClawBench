"""The reproduction CLI must never own its caller's entire work directory."""

from pathlib import Path

import pytest

from clawbench.eval import reproduce


@pytest.mark.parametrize(
    "outcome", ["pass", "fail", "download_error", "judge_error", "interrupt"]
)
@pytest.mark.parametrize("keep_cache", [False, True])
def test_cli_preserves_user_files_and_cleans_only_its_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str, keep_cache: bool
) -> None:
    work_dir = tmp_path / "existing-work"
    work_dir.mkdir()
    sentinel = work_dir / "unrelated.txt"
    sentinel.write_text("user data")
    previous_cache = work_dir / "clawbench-previous"
    previous_cache.mkdir()
    (previous_cache / "trace.json").write_text("previous run")
    destinations = []

    def download(model: str, dest: Path) -> Path:
        destinations.append(dest)
        assert dest.parent == work_dir
        assert dest != previous_cache
        (dest / "download.txt").write_text("owned download")
        if outcome == "download_error":
            raise SystemExit("download failed")
        batch = dest / "traces"
        batch.mkdir()
        return batch

    def rescore(batch_dir: Path, judge_model: str, rubric: str) -> dict:
        if outcome == "judge_error":
            raise RuntimeError("judge failed")
        if outcome == "interrupt":
            raise KeyboardInterrupt
        return {
            "n_total": 129,
            "n_intercepted": 4 if outcome == "pass" else 129,
            "reward_pct_lenient": 3 / 129,
            "reward_pct_strict": 0,
        }

    monkeypatch.setattr(reproduce, "download", download)
    monkeypatch.setattr(reproduce, "rescore", rescore)
    argv = [
        "clawbench-reproduce",
        "--model",
        "deepseek-v4-flash",
        "--work-dir",
        str(work_dir),
    ]
    if keep_cache:
        argv.append("--keep-cache")
    monkeypatch.setattr("sys.argv", argv)
    errors = {
        "download_error": SystemExit,
        "judge_error": RuntimeError,
        "interrupt": KeyboardInterrupt,
    }
    if outcome in errors:
        with pytest.raises(errors[outcome]):
            reproduce.main()
    else:
        assert reproduce.main() == (0 if outcome == "pass" else 1)

    assert sentinel.read_text() == "user data"
    assert (previous_cache / "trace.json").read_text() == "previous run"
    assert len(destinations) == 1
    assert destinations[0].exists() is keep_cache
    if keep_cache:
        assert (destinations[0] / "download.txt").read_text() == "owned download"


def test_overlapping_invocations_have_independent_caches(tmp_path: Path) -> None:
    with reproduce.download_cache(tmp_path, False) as first:
        (first / "active.txt").write_text("first run")
        with reproduce.download_cache(tmp_path, False) as second:
            assert second != first
            assert first.is_dir() and second.is_dir()
        assert not second.exists()
        assert (first / "active.txt").read_text() == "first run"
    assert not first.exists()
    assert tmp_path.is_dir()
