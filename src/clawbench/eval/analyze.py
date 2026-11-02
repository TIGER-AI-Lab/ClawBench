"""``clawbench-analyze`` — aggregate error analysis over a batch of run outputs (#159).

Reads a directory of completed run outputs (each ``<run>/data/interception.json``,
optionally ``<run>/judge_llm.json``, ``<run>/judge.json``, ``<run>/reward.json``),
reuses the per-run classifier, and produces an aggregate report: Stage-1
(interception) and Stage-2 (judged) rates, overall two-stage success rate over
all runs, judgment coverage, per-category breakdown, failure taxonomy, the
interceptor false-positive check, and the self-report-vs-actual gap. Output as
Markdown and/or JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from clawbench.runner.run_support.results import classify_run

VALID_RUBRICS = ("auto", "lenient", "strict", "both")

# heuristic: an agent message claiming the task is finished
_CLAIM_RE = re.compile(
    r"\b(task (is )?(complete|completed|done|finished|accomplished)|"
    r"successfully (completed|submitted|saved|booked)|i (have|'ve) (completed|finished|done))\b",
    re.IGNORECASE,
)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def _task_category(
    run_dir: Path,
    task: dict[str, Any] | None,
    run_meta: dict[str, Any] | None = None,
) -> str:
    """Category from task metadata, else derived from the task-id name segments."""
    if isinstance(run_meta, dict):
        for key in ("metaclass", "category"):
            if run_meta.get(key):
                return str(run_meta[key])
    if isinstance(task, dict):
        meta = task.get("metadata")
        if isinstance(meta, dict):
            for key in ("metaclass", "category"):
                if meta.get(key):
                    return str(meta[key])
    # e.g. "v2-536-daily-life-shopping-etsy" -> "daily-life-shopping"
    task_name = (
        str(run_meta.get("test_case"))
        if isinstance(run_meta, dict) and run_meta.get("test_case")
        else run_dir.name
    )
    parts = task_name.split("-")
    if len(parts) >= 4 and parts[0].startswith("v"):
        return "-".join(parts[2:-1]) or "uncategorized"
    if len(parts) >= 3 and parts[0].isdigit():
        return "-".join(parts[1:-1]) or "uncategorized"
    return "uncategorized"


def _claimed_success(run_dir: Path) -> bool:
    msgs = run_dir / "data" / "agent-messages.jsonl"
    if not msgs.is_file():
        return False
    try:
        with msgs.open(errors="replace") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                stack = [event]
                while stack:
                    value = stack.pop()
                    if isinstance(value, dict):
                        if (
                            value.get("role") == "assistant"
                            or value.get("type") == "assistant"
                        ):
                            if _CLAIM_RE.search(json.dumps(value, ensure_ascii=False)):
                                return True
                            continue
                        stack.extend(value.values())
                    elif isinstance(value, list):
                        stack.extend(value)
    except OSError:
        return False
    return False


def _extract_judge_model(
    verdict: dict[str, Any] | None,
    run_meta: dict[str, Any] | None = None,
    *,
    allow_run_meta: bool = False,
) -> str | None:
    if isinstance(verdict, dict):
        for key in ("judge_model", "model"):
            val = verdict.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    if allow_run_meta and isinstance(run_meta, dict):
        val = run_meta.get("judge_model")
        if isinstance(val, str) and val.strip():
            return val.strip()
        flags = run_meta.get("run_flags")
        if isinstance(flags, dict):
            judge_flag = flags.get("judge")
            if isinstance(judge_flag, str) and judge_flag.strip():
                return judge_flag.strip()
    return None


def _finalize_verdict(
    *,
    rubric: str,
    intercepted: bool,
    raw_match: bool | None,
    has_artifact: bool,
    inconclusive: bool,
    judge_model: str | None,
    source: str | None,
) -> dict[str, Any]:
    if not intercepted:
        if raw_match is True:
            return {
                "rubric": rubric,
                "judged": None,
                "two_stage_pass": False,
                "judge_status": "stale_unintercepted",
                "judge_model": judge_model,
                "source": source,
                "has_artifact": has_artifact,
            }
        if raw_match is False:
            return {
                "rubric": rubric,
                "judged": False,
                "two_stage_pass": False,
                "judge_status": "fail",
                "judge_model": judge_model,
                "source": source,
                "has_artifact": has_artifact,
            }
        return {
            "rubric": rubric,
            "judged": None,
            "two_stage_pass": False,
            "judge_status": "inconclusive" if inconclusive else "unjudged",
            "judge_model": judge_model,
            "source": source,
            "has_artifact": has_artifact,
        }

    if raw_match is True:
        status = "pass"
    elif raw_match is False:
        status = "fail"
    elif inconclusive:
        status = "inconclusive"
    else:
        status = "unjudged"

    return {
        "rubric": rubric,
        "judged": raw_match,
        "two_stage_pass": raw_match is True,
        "judge_status": status,
        "judge_model": judge_model,
        "source": source,
        "has_artifact": has_artifact,
    }


def _read_lenient_verdict(run_dir: Path, intercepted: bool) -> dict[str, Any]:
    judge_llm = _read_json(run_dir / "judge_llm.json") or _read_json(
        run_dir / "data" / "judge_llm.json"
    )
    if isinstance(judge_llm, dict):
        model = _extract_judge_model(judge_llm)
        match = judge_llm.get("match")
        if isinstance(match, bool):
            return _finalize_verdict(
                rubric="lenient",
                intercepted=intercepted,
                raw_match=match,
                has_artifact=True,
                inconclusive=False,
                judge_model=model,
                source="judge_llm.json",
            )
        if "match" in judge_llm and match is None:
            return _finalize_verdict(
                rubric="lenient",
                intercepted=intercepted,
                raw_match=None,
                has_artifact=True,
                inconclusive=True,
                judge_model=model,
                source="judge_llm.json",
            )

    detailed = _read_json(run_dir / "clawbench-result.json")
    if isinstance(detailed, dict) and (
        "judge_match_lenient" in detailed or "reward_lenient" in detailed
    ):
        model = _extract_judge_model(detailed)
        jm = detailed.get("judge_match_lenient")
        if isinstance(jm, bool):
            return _finalize_verdict(
                rubric="lenient",
                intercepted=intercepted,
                raw_match=jm,
                has_artifact=True,
                inconclusive=False,
                judge_model=model,
                source="clawbench-result.json",
            )
        if "judge_match_lenient" in detailed and jm is None:
            return _finalize_verdict(
                rubric="lenient",
                intercepted=intercepted,
                raw_match=None,
                has_artifact=True,
                inconclusive=True,
                judge_model=model,
                source="clawbench-result.json",
            )

    reward = _read_json(run_dir / "reward.json")
    if isinstance(reward, dict) and (
        "judge_match_lenient" in reward or "reward_lenient" in reward
    ):
        model = _extract_judge_model(reward)
        jm = reward.get("judge_match_lenient")
        if isinstance(jm, bool):
            raw = jm
        elif isinstance(jm, (int, float)):
            raw = float(jm) >= 1.0
        elif "judge_match_lenient" in reward and jm is None:
            return _finalize_verdict(
                rubric="lenient",
                intercepted=intercepted,
                raw_match=None,
                has_artifact=True,
                inconclusive=True,
                judge_model=model,
                source="reward.json",
            )
        elif isinstance(reward.get("reward_lenient"), (int, float)):
            raw = float(reward["reward_lenient"]) >= 1.0
        else:
            raw = None
        if raw is not None:
            return _finalize_verdict(
                rubric="lenient",
                intercepted=intercepted,
                raw_match=raw,
                has_artifact=True,
                inconclusive=False,
                judge_model=model,
                source="reward.json",
            )

    return _finalize_verdict(
        rubric="lenient",
        intercepted=intercepted,
        raw_match=None,
        has_artifact=False,
        inconclusive=False,
        judge_model=None,
        source=None,
    )


def _read_strict_verdict(
    run_dir: Path, run_meta: dict[str, Any] | None, intercepted: bool
) -> dict[str, Any]:
    judge = _read_json(run_dir / "judge.json") or _read_json(
        run_dir / "data" / "judge.json"
    )
    if isinstance(judge, dict):
        model = _extract_judge_model(judge, run_meta, allow_run_meta=True)
        match = judge.get("match")
        if isinstance(match, bool):
            return _finalize_verdict(
                rubric="strict",
                intercepted=intercepted,
                raw_match=match,
                has_artifact=True,
                inconclusive=False,
                judge_model=model,
                source="judge.json",
            )
        if "match" in judge and match is None:
            return _finalize_verdict(
                rubric="strict",
                intercepted=intercepted,
                raw_match=None,
                has_artifact=True,
                inconclusive=True,
                judge_model=model,
                source="judge.json",
            )

    if isinstance(run_meta, dict):
        model = _extract_judge_model(None, run_meta, allow_run_meta=True)
        if isinstance(run_meta.get("judge_match"), bool):
            return _finalize_verdict(
                rubric="strict",
                intercepted=intercepted,
                raw_match=run_meta["judge_match"],
                has_artifact=True,
                inconclusive=False,
                judge_model=model,
                source="run-meta.json",
            )
        if (
            ("judge_match" in run_meta and run_meta.get("judge_match") is None)
            or run_meta.get("result_category") == "judge_inconclusive"
            or run_meta.get("failure_category") == "judge_inconclusive"
        ):
            return _finalize_verdict(
                rubric="strict",
                intercepted=intercepted,
                raw_match=None,
                has_artifact=True,
                inconclusive=True,
                judge_model=model,
                source="run-meta.json",
            )

    detailed = _read_json(run_dir / "clawbench-result.json")
    if isinstance(detailed, dict):
        model = _extract_judge_model(detailed, run_meta, allow_run_meta=True)
        for key in ("judge_match_strict", "judge_match"):
            if key in detailed:
                jm = detailed.get(key)
                if isinstance(jm, bool):
                    return _finalize_verdict(
                        rubric="strict",
                        intercepted=intercepted,
                        raw_match=jm,
                        has_artifact=True,
                        inconclusive=False,
                        judge_model=model,
                        source="clawbench-result.json",
                    )
                if jm is None:
                    return _finalize_verdict(
                        rubric="strict",
                        intercepted=intercepted,
                        raw_match=None,
                        has_artifact=True,
                        inconclusive=True,
                        judge_model=model,
                        source="clawbench-result.json",
                    )

    reward = _read_json(run_dir / "reward.json")
    if isinstance(reward, dict):
        model = _extract_judge_model(reward, run_meta, allow_run_meta=True)
        for key in ("judge_match_strict", "judge_match"):
            if key in reward:
                jm = reward.get(key)
                if isinstance(jm, bool):
                    raw = jm
                elif isinstance(jm, (int, float)):
                    raw = float(jm) >= 1.0
                elif jm is None:
                    return _finalize_verdict(
                        rubric="strict",
                        intercepted=intercepted,
                        raw_match=None,
                        has_artifact=True,
                        inconclusive=True,
                        judge_model=model,
                        source="reward.json",
                    )
                else:
                    raw = None
                if raw is not None:
                    return _finalize_verdict(
                        rubric="strict",
                        intercepted=intercepted,
                        raw_match=raw,
                        has_artifact=True,
                        inconclusive=False,
                        judge_model=model,
                        source="reward.json",
                    )
        for key in ("reward_strict", "reward"):
            if isinstance(reward.get(key), (int, float)):
                return _finalize_verdict(
                    rubric="strict",
                    intercepted=intercepted,
                    raw_match=float(reward[key]) >= 1.0,
                    has_artifact=True,
                    inconclusive=False,
                    judge_model=model,
                    source="reward.json",
                )

    return _finalize_verdict(
        rubric="strict",
        intercepted=intercepted,
        raw_match=None,
        has_artifact=False,
        inconclusive=False,
        judge_model=_extract_judge_model(None, run_meta, allow_run_meta=True),
        source=None,
    )


def discover_runs(runs_dir: Path) -> list[Path]:
    """Discover canonical runs recursively, with an interception-only fallback."""
    runs = {p.parent for p in runs_dir.rglob("run-meta.json")}
    runs.update(p.parent.parent for p in runs_dir.rglob("data/interception.json"))
    return sorted(runs)


def run_summary(run_dir: Path, rubric: str = "auto") -> dict[str, Any]:
    """Per-run: task id/category, Stage-1 intercept, Stage-2 judged, failure class."""
    if rubric not in VALID_RUBRICS:
        raise ValueError(
            f"Unsupported rubric {rubric!r}; expected one of {VALID_RUBRICS}"
        )

    run_meta = _read_json(run_dir / "run-meta.json")
    interception = _read_json(run_dir / "data" / "interception.json")
    if isinstance(run_meta, dict) and isinstance(run_meta.get("intercepted"), bool):
        intercepted = run_meta["intercepted"]
    else:
        intercepted = bool(
            isinstance(interception, dict) and interception.get("intercepted")
        )
    task = _read_json(run_dir / "data" / "task.json") or _read_json(
        run_dir / "task.json"
    )

    lenient_info = _read_lenient_verdict(run_dir, intercepted)
    strict_info = _read_strict_verdict(
        run_dir, run_meta if isinstance(run_meta, dict) else None, intercepted
    )
    verdicts = {"lenient": lenient_info, "strict": strict_info}

    if rubric in ("lenient", "strict"):
        selected_rubric = rubric
    elif lenient_info["has_artifact"]:
        selected_rubric = "lenient"
    elif strict_info["has_artifact"]:
        selected_rubric = "strict"
    else:
        selected_rubric = "lenient"

    selected = verdicts[selected_rubric]

    cls = classify_run(run_dir, intercepted, recording_required=False)
    meta_metrics = run_meta.get("run_metrics") if isinstance(run_meta, dict) else None
    actions = meta_metrics.get("actions") if isinstance(meta_metrics, dict) else None
    result_category = (
        run_meta.get("result_category")
        if isinstance(run_meta, dict) and run_meta.get("result_category")
        else cls.get("result_category")
    )
    if intercepted and selected["judge_status"] == "inconclusive":
        result_category = "judge_inconclusive"

    return {
        "task": (
            str(run_meta.get("test_case"))
            if isinstance(run_meta, dict) and run_meta.get("test_case")
            else run_dir.name
        ),
        "category": _task_category(
            run_dir,
            task if isinstance(task, dict) else None,
            run_meta if isinstance(run_meta, dict) else None,
        ),
        "intercepted": intercepted,
        "rubric": selected_rubric,
        "judged": selected["judged"],
        "two_stage_pass": selected["two_stage_pass"],
        "judge_status": selected["judge_status"],
        "judge_model": selected["judge_model"],
        "judge_source": selected["source"],
        "verdicts": verdicts,
        "result_category": result_category,
        "actions": actions
        if isinstance(actions, int)
        else cls.get("metrics", {}).get("actions", 0),
        "claimed_success": _claimed_success(run_dir),
    }


def _summarize_rubric(runs: list[dict[str, Any]], rubric_name: str) -> dict[str, Any]:
    n = len(runs)
    intercepted = sum(1 for r in runs if r["intercepted"])
    have_judge = [r for r in runs if r["verdicts"][rubric_name]["judged"] is not None]
    judged_intercepted = [
        r
        for r in runs
        if r["intercepted"] and r["verdicts"][rubric_name]["judged"] is not None
    ]
    judged_pass = sum(
        1
        for r in runs
        if r["intercepted"] and r["verdicts"][rubric_name]["judged"] is True
    )
    judged_fail = sum(
        1 for r in have_judge if r["verdicts"][rubric_name]["judged"] is False
    )
    inconclusive = sum(
        1
        for r in runs
        if r["intercepted"]
        and r["verdicts"][rubric_name]["judge_status"] == "inconclusive"
    )
    missing = sum(
        1
        for r in runs
        if r["intercepted"] and r["verdicts"][rubric_name]["judge_status"] == "unjudged"
    )
    unjudged = sum(
        1
        for r in runs
        if r["intercepted"] and r["verdicts"][rubric_name]["judged"] is None
    )
    stale_unintercepted = sum(
        1
        for r in runs
        if not r["intercepted"]
        and r["verdicts"][rubric_name]["judge_status"] == "stale_unintercepted"
    )
    judge_models = sorted(
        {
            str(m)
            for r in runs
            if r["verdicts"][rubric_name]["has_artifact"]
            and (m := r["verdicts"][rubric_name]["judge_model"])
        }
    )
    overall_rate = (
        round(judged_pass / n, 4) if (n and (have_judge or intercepted == 0)) else None
    )
    return {
        "rubric": rubric_name,
        "judge_model": judge_models[0] if len(judge_models) == 1 else None,
        "judge_models": judge_models,
        "stage2_judged_of": len(have_judge),
        "stage2_pass": judged_pass,
        "stage2_fail": judged_fail,
        "stage2_rate": round(judged_pass / len(have_judge), 4) if have_judge else None,
        "stage2_overall_pass": judged_pass,
        "stage2_overall_rate": overall_rate,
        "two_stage_pass": judged_pass,
        "two_stage_rate": overall_rate,
        "stage2_coverage": round(len(have_judge) / n, 4) if n else 0.0,
        "stage2_intercepted_coverage": round(len(judged_intercepted) / intercepted, 4)
        if intercepted
        else None,
        "stage2_inconclusive": inconclusive,
        "stage2_missing": missing,
        "stage2_unjudged": unjudged,
        "stage2_stale_unintercepted": stale_unintercepted,
    }


def analyze_batch(runs_dir: Path, rubric: str = "auto") -> dict[str, Any]:
    """Aggregate the per-run summaries into an error-analysis report dict."""
    if rubric not in VALID_RUBRICS:
        raise ValueError(
            f"Unsupported rubric {rubric!r}; expected one of {VALID_RUBRICS}"
        )

    runs = [run_summary(r, rubric=rubric) for r in discover_runs(runs_dir)]
    n = len(runs)
    intercepted = sum(1 for r in runs if r["intercepted"])

    by_rubric = {
        "lenient": _summarize_rubric(runs, "lenient"),
        "strict": _summarize_rubric(runs, "strict"),
    }

    if rubric in ("lenient", "strict"):
        selected_rubric = rubric
    elif any(r["verdicts"]["lenient"]["has_artifact"] for r in runs):
        selected_rubric = "lenient"
    elif any(r["verdicts"]["strict"]["has_artifact"] for r in runs):
        selected_rubric = "strict"
    else:
        selected_rubric = "lenient"

    # Bind every run to the batch's selected rubric so a missing lenient verdict
    # on one run never falls back to an older strict/native verdict.
    for r in runs:
        sel = r["verdicts"][selected_rubric]
        r["rubric"] = selected_rubric
        r["judged"] = sel["judged"]
        r["two_stage_pass"] = sel["two_stage_pass"]
        r["judge_status"] = sel["judge_status"]
        r["judge_model"] = sel["judge_model"]
        r["judge_source"] = sel["source"]
        if r["intercepted"] and sel["judge_status"] == "inconclusive":
            r["result_category"] = "judge_inconclusive"

    selected_stats = by_rubric[selected_rubric]

    # per-category Stage-1 breakdown
    by_cat: dict[str, dict[str, int]] = {}
    for r in runs:
        c = by_cat.setdefault(r["category"], {"n": 0, "intercepted": 0})
        c["n"] += 1
        c["intercepted"] += int(r["intercepted"])

    # validity checks
    zero_action_intercepted = sum(
        1 for r in runs if r["actions"] == 0 and r["intercepted"]
    )

    # self-report gap: claimed success but did NOT pass (judged False, or not intercepted)
    def _failed(r: dict[str, Any]) -> bool:
        return (r["judged"] is False) or (r["judged"] is None and not r["intercepted"])

    claimed_but_failed = sum(1 for r in runs if r["claimed_success"] and _failed(r))
    claimed_total = sum(1 for r in runs if r["claimed_success"])

    return {
        "n_runs": n,
        "rubric": selected_rubric,
        "requested_rubric": rubric,
        "judge_model": selected_stats["judge_model"],
        "judge_models": selected_stats["judge_models"],
        "stage1_intercepted": intercepted,
        "stage1_rate": round(intercepted / n, 4) if n else 0.0,
        "stage2_judged_of": selected_stats["stage2_judged_of"],
        "stage2_pass": selected_stats["stage2_pass"],
        "stage2_fail": selected_stats["stage2_fail"],
        "stage2_rate": selected_stats["stage2_rate"],
        "stage2_overall_pass": selected_stats["stage2_overall_pass"],
        "stage2_overall_rate": selected_stats["stage2_overall_rate"],
        "two_stage_pass": selected_stats["two_stage_pass"],
        "two_stage_rate": selected_stats["two_stage_rate"],
        "stage2_coverage": selected_stats["stage2_coverage"],
        "stage2_intercepted_coverage": selected_stats["stage2_intercepted_coverage"],
        "stage2_inconclusive": selected_stats["stage2_inconclusive"],
        "stage2_missing": selected_stats["stage2_missing"],
        "stage2_unjudged": selected_stats["stage2_unjudged"],
        "stage2_stale_unintercepted": selected_stats["stage2_stale_unintercepted"],
        "by_rubric": by_rubric,
        "failure_taxonomy": dict(Counter(r["result_category"] for r in runs)),
        "by_category": {
            k: {**v, "rate": round(v["intercepted"] / v["n"], 4)}
            for k, v in sorted(by_cat.items())
        },
        "interceptor_false_positives": zero_action_intercepted,  # should be 0
        "self_report_claimed": claimed_total,
        "self_report_claimed_but_failed": claimed_but_failed,
    }


def format_report(stats: dict[str, Any]) -> str:
    n = stats["n_runs"]
    rubric = stats.get("rubric", "lenient")
    judge_models = stats.get("judge_models") or (
        [stats["judge_model"]] if stats.get("judge_model") else []
    )
    judge_label = ", ".join(judge_models) if judge_models else "unspecified"

    lines = ["# ClawBench batch error analysis", ""]
    lines.append(f"- **Runs:** {n}")
    lines.append(f"- **Rubric:** {rubric} (judge: {judge_label})")
    lines.append(
        f"- **Stage-1 intercepted:** {stats['stage1_intercepted']}/{n} "
        f"({stats['stage1_rate']:.0%})"
    )
    if stats["stage2_rate"] is not None:
        lines.append(
            f"- **Stage-2 judged pass:** {stats['stage2_pass']}/{stats['stage2_judged_of']} "
            f"({stats['stage2_rate']:.0%})"
        )
    overall_rate = stats.get("stage2_overall_rate")
    overall_pass = stats.get("stage2_overall_pass", stats.get("stage2_pass", 0))
    if overall_rate is not None:
        lines.append(
            f"- **Overall two-stage success:** {overall_pass}/{n} ({overall_rate:.0%})"
        )
    coverage = stats.get("stage2_coverage")
    if coverage is not None:
        lines.append(
            f"- **Stage-2 judgment coverage:** {stats['stage2_judged_of']}/{n} "
            f"({coverage:.0%})"
        )
    if stats.get("stage2_inconclusive"):
        lines.append(
            f"- **Stage-2 inconclusive judgments:** {stats['stage2_inconclusive']}"
        )
    if stats.get("stage2_missing"):
        lines.append(
            f"- **Stage-2 missing judgments (intercepted):** {stats['stage2_missing']}"
        )
    lines.append(
        f"- **Interceptor false-positives** (0-action but intercepted): "
        f"{stats['interceptor_false_positives']} (should be 0)"
    )
    if stats["self_report_claimed"]:
        lines.append(
            f"- **Self-report gap:** {stats['self_report_claimed_but_failed']}/"
            f"{stats['self_report_claimed']} runs that claimed success actually failed"
        )

    by_rubric = stats.get("by_rubric")
    if isinstance(by_rubric, dict) and (
        stats.get("requested_rubric") == "both"
        or sum(1 for r in by_rubric.values() if r.get("stage2_judged_of", 0) > 0) > 1
    ):
        lines += [
            "",
            "## Stage-2 by rubric",
            "",
            "| rubric | judge | judged | pass (among judged) | overall two-stage | inconclusive | missing |",
            "|---|---|--:|--:|--:|--:|--:|",
        ]
        for r_name in ("lenient", "strict"):
            r_stats = by_rubric.get(r_name)
            if not isinstance(r_stats, dict):
                continue
            r_judges = ", ".join(r_stats.get("judge_models") or []) or "unspecified"
            r_rate = (
                f"{r_stats['stage2_pass']}/{r_stats['stage2_judged_of']} ({r_stats['stage2_rate']:.0%})"
                if r_stats.get("stage2_rate") is not None
                else "n/a"
            )
            r_overall = (
                f"{r_stats['stage2_overall_pass']}/{n} ({r_stats['stage2_overall_rate']:.0%})"
                if r_stats.get("stage2_overall_rate") is not None
                else "n/a"
            )
            lines.append(
                f"| {r_name} | {r_judges} | {r_stats['stage2_judged_of']}/{n} | "
                f"{r_rate} | {r_overall} | {r_stats['stage2_inconclusive']} | {r_stats['stage2_missing']} |"
            )

    lines += ["", "## Failure taxonomy", ""]
    for k, v in sorted(stats["failure_taxonomy"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k or 'unknown'}: {v}")
    lines += [
        "",
        "## Per-category Stage-1",
        "",
        "| category | n | intercepted | rate |",
        "|---|--:|--:|--:|",
    ]
    for cat, v in stats["by_category"].items():
        lines.append(f"| {cat} | {v['n']} | {v['intercepted']} | {v['rate']:.0%} |")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clawbench-analyze",
        description="Aggregate error analysis over a batch of ClawBench run outputs.",
    )
    p.add_argument(
        "--runs-dir",
        type=Path,
        required=True,
        help="Batch output dir (contains <run>/data/)",
    )
    p.add_argument(
        "--rubric",
        choices=list(VALID_RUBRICS),
        default="auto",
        help="Judge rubric to analyze: 'lenient' (judge_llm.json), 'strict' (judge.json / native), "
        "'both', or 'auto' (prefers lenient rescore when present).",
    )
    p.add_argument(
        "--out", type=Path, default=None, help="Write the Markdown report here"
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print the stats as JSON instead of Markdown",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.runs_dir.is_dir():
        print(f"ERROR: runs dir not found: {args.runs_dir}", file=sys.stderr)
        return 1
    stats = analyze_batch(args.runs_dir, rubric=args.rubric)
    if stats["n_runs"] == 0:
        print(f"ERROR: no runs found under {args.runs_dir}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        report = format_report(stats)
        if args.out:
            args.out.write_text(report)
            print(f"Wrote report to {args.out}")
        else:
            print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
