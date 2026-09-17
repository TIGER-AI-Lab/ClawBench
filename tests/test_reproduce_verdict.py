"""A reproduction verdict must rest on complete evidence for the requested rubrics."""

from pathlib import Path
from typing import Any

import pytest

from clawbench.eval import reproduce

MODEL = "claude-opus-4-7"
PUBLISHED = reproduce.PUBLISHED_V2_HERMES[MODEL]


def _rescore_summary(rubrics: list[str], **overrides: Any) -> dict[str, Any]:
    """A rescore summary matching the published row for the rubrics that ran."""
    n = PUBLISHED[3]
    summary: dict[str, Any] = {
        "n_total": n,
        "n_intercepted": round(PUBLISHED[0] * n / 100),
        "rubrics": rubrics,
    }
    for rubric, pct in (("lenient", PUBLISHED[1]), ("strict", PUBLISHED[2])):
        if rubric in rubrics:
            summary[f"reward_pct_{rubric}"] = pct / 100
            summary[f"n_judge_err_{rubric}"] = 0
    summary.update(overrides)
    return summary


def test_matching_percentages_on_a_different_sample_are_invalid() -> None:
    outcome, table = reproduce.verdict((50, 40, 20, 5), (50, 40, 20, 130), 2)

    assert outcome == "invalid"
    assert "5" in table and "130" in table


@pytest.mark.parametrize("rubric", ["lenient", "strict"])
def test_single_rubric_compares_only_the_requested_column(rubric: str) -> None:
    summary = _rescore_summary([rubric])
    observed = reproduce.observed_metrics(summary)

    outcome, table = reproduce.verdict(observed, PUBLISHED, 2, rubric=rubric)

    assert outcome == "pass"
    assert table.count("not evaluated") == 1
    assert "FAIL" not in table


def test_full_mode_passes_and_reports_a_measured_mismatch() -> None:
    matching = reproduce.observed_metrics(_rescore_summary(["lenient", "strict"]))
    drifted = reproduce.observed_metrics(
        _rescore_summary(["lenient", "strict"], reward_pct_lenient=0.10)
    )

    assert reproduce.verdict(matching, PUBLISHED, 2)[0] == "pass"
    outcome, table = reproduce.verdict(drifted, PUBLISHED, 2)
    assert outcome == "fail"
    assert "FAIL" in table


def test_missing_requested_metric_is_invalid_not_zero() -> None:
    observed = reproduce.observed_metrics(_rescore_summary(["lenient"]))

    outcome, table = reproduce.verdict(observed, PUBLISHED, 2, rubric="both")

    assert outcome == "invalid"
    assert "missing" in table
    assert "0.0%" not in table


def test_judge_inconclusive_results_are_invalid() -> None:
    summary = _rescore_summary(["lenient", "strict"], n_judge_err_lenient=3)

    outcome, table = reproduce.verdict(
        reproduce.observed_metrics(summary),
        PUBLISHED,
        2,
        inconclusive=reproduce.inconclusive_count(summary, "both"),
    )

    assert outcome == "invalid"
    assert "judge inconclusive" in table


def test_inconclusive_results_of_an_unrequested_rubric_are_ignored() -> None:
    summary = _rescore_summary(["lenient", "strict"], n_judge_err_strict=3)

    assert reproduce.inconclusive_count(summary, "lenient") == 0
    assert reproduce.inconclusive_count(summary, "both") == 3


def test_empty_input_is_invalid() -> None:
    summary = {"n_total": 0, "n_intercepted": 0}

    outcome, _ = reproduce.verdict(reproduce.observed_metrics(summary), PUBLISHED, 2)

    assert outcome == "invalid"
    assert reproduce.verdict((0, 0, 0, 0), (0, 0, 0, 0), 2)[0] == "invalid"


@pytest.mark.parametrize(
    ("rubric", "summary", "exit_code"),
    [
        ("both", _rescore_summary(["lenient", "strict"]), 0),
        ("lenient", _rescore_summary(["lenient"]), 0),
        ("strict", _rescore_summary(["strict"]), 0),
        ("both", _rescore_summary(["lenient", "strict"], reward_pct_strict=0.90), 1),
        ("both", _rescore_summary(["lenient"]), 3),
        (
            "both",
            _rescore_summary(["lenient", "strict"], n_total=5, n_intercepted=3),
            3,
        ),
        ("lenient", _rescore_summary(["lenient"], n_judge_err_lenient=2), 3),
    ],
)
def test_cli_exit_status_separates_mismatch_from_invalid_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rubric: str,
    summary: dict[str, Any],
    exit_code: int,
) -> None:
    def download(model: str, dest: Path) -> Path:
        batch = dest / "traces"
        batch.mkdir()
        return batch

    def rescore(batch_dir: Path, judge_model: str, requested: str) -> dict[str, Any]:
        assert requested == rubric
        return summary

    monkeypatch.setattr(reproduce, "download", download)
    monkeypatch.setattr(reproduce, "rescore", rescore)
    monkeypatch.setattr(
        "sys.argv",
        [
            "clawbench-reproduce",
            "--model",
            MODEL,
            "--rubric",
            rubric,
            "--work-dir",
            str(tmp_path),
        ],
    )

    assert reproduce.main() == exit_code
    printed = capsys.readouterr().out
    assert ("PASS" in printed) is (exit_code == 0)
    assert ("INVALID" in printed) is (exit_code == 3)
