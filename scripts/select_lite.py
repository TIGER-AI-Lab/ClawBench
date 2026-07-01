#!/usr/bin/env python3
"""Select CLAWBENCH-LITE: 30 representative v2 tasks for low-cost evaluation.

The full CLAWBENCH v2 pool has 130 tasks across exactly **30 scenario
classes** (``metadata.metaclass``). CLAWBENCH-LITE takes *one representative
per scenario class* (30 -> 30), and among the candidates of each class picks
the one that best preserves coverage along four further axes the proposal
calls out:

  1. scenario class      -- one representative per ``metaclass`` (hard constraint)
  2. platform diversity  -- maximise distinct ``metadata.platform``
  3. outcome request     -- HTTP ``method`` (POST/GET/PUT) + GraphQL constraint
  4. pilot failure regime-- reach band from the pilot's per-task taxonomy
                            (unreached / hard / mixed), so LITE keeps the
                            main failure modes, not just the easy tasks

A fifth axis in the proposal -- *execution mode* (repeatable-online /
reset-required / offline-only) -- is **not annotated** in the task pool yet.
We surface a provisional keyword-derived label in the report (clearly marked
``provisional``) but do NOT let it drive selection.

The selector is fully deterministic: no randomness, stable tie-breaks. Same
inputs -> identical LITE set, which is what a released benchmark subset needs.

Usage::

    python scripts/select_lite.py --check          # report coverage, no writes
    python scripts/select_lite.py --write          # materialise test-cases/v2-lite/
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_V2 = REPO_ROOT / "test-cases" / "v2"
# Frozen snapshot of the pilot per-task reach/failure aggregates (across 8
# models), committed alongside the selector so the LITE set is reproducible
# without the untracked exps/ analysis tree. Regenerate with:
#   cp exps/v2_url_complexity/per_task_taxonomy.json scripts/data/pilot_per_task_taxonomy.json
TAXONOMY_JSON = REPO_ROOT / "scripts" / "data" / "pilot_per_task_taxonomy.json"
DEFAULT_OUT = REPO_ROOT / "test-cases" / "v2-lite"

SELECTOR_VERSION = "1.0.0"
LITE_TARGET = 30  # == number of scenario classes

# Keywords -> provisional execution-mode label (report only; see module docstring).
_RESET_HINTS = ("sign up", "register", "create an account", "signup", "enroll", "create account")
_OFFLINE_HINTS = ("pay ", "payment", "checkout", "purchase", "credit card", "government id")


def _reach_band(rate: float) -> str:
    """Bucket a pilot reach-rate (n_intercepted / n_runs) into a failure regime."""
    if rate <= 0.0:
        return "unreached"
    if rate <= 1 / 3:
        return "hard"
    if rate <= 2 / 3:
        return "mixed"
    return "reachable"


def _provisional_exec_mode(text: str) -> str:
    low = text.lower()
    if any(h in low for h in _OFFLINE_HINTS):
        return "offline-only"
    if any(h in low for h in _RESET_HINTS):
        return "reset-required"
    return "repeatable-online"


@dataclasses.dataclass(frozen=True, slots=True)
class TaskFeat:
    task_dir: str  # directory name, e.g. "v2-047-daily-life-personal-care-taskrabbit"
    task_id: int
    metaclass: str
    cls: str
    platform: str
    method: str
    is_graphql: bool
    n_runs: int
    n_intercepted: int
    reach_rate: float
    reach_band: str
    dominant_fail_cat: str
    exec_mode_provisional: str


def _taxonomy_key(task_dir: str) -> str:
    return task_dir[3:] if task_dir.startswith("v2-") else task_dir


def load_features(tasks_dir: Path = TASKS_V2, taxonomy_json: Path = TAXONOMY_JSON) -> list[TaskFeat]:
    if not tasks_dir.is_dir():
        raise FileNotFoundError(f"v2 task pool not found: {tasks_dir}")
    taxonomy: dict[str, Any] = json.loads(taxonomy_json.read_text()) if taxonomy_json.is_file() else {}

    feats: list[TaskFeat] = []
    for task_path in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        task_json = task_path / "task.json"
        if not task_json.is_file():
            continue
        d = json.loads(task_json.read_text())
        meta = d.get("metadata", {})
        es = d.get("eval_schema", {}) or {}
        es_blob = json.dumps(es).lower()

        tax = taxonomy.get(_taxonomy_key(task_path.name), {})
        n_runs = int(tax.get("n_runs", 0))
        n_int = int(tax.get("n_intercepted", 0))
        rate = (n_int / n_runs) if n_runs else 0.0
        cats: dict[str, int] = tax.get("cats", {}) or {}
        dom_cat = max(cats, key=cats.get) if cats else ""

        text = f"{d.get('instruction', '')} {meta.get('description', '')}"
        feats.append(
            TaskFeat(
                task_dir=task_path.name,
                task_id=int(meta.get("task_id", -1)),
                metaclass=str(meta.get("metaclass", "unknown")),
                cls=str(meta.get("class", "unknown")),
                platform=str(meta.get("platform", "unknown")),
                method=str(es.get("method", "UNKNOWN")).upper(),
                is_graphql=("graphql" in es_blob),
                n_runs=n_runs,
                n_intercepted=n_int,
                reach_rate=rate,
                reach_band=_reach_band(rate),
                dominant_fail_cat=dom_cat,
                exec_mode_provisional=_provisional_exec_mode(text),
            )
        )
    return feats


def select_lite(feats: list[TaskFeat], *, k: int = LITE_TARGET) -> list[TaskFeat]:
    """Deterministically pick one task per scenario class, maximising coverage.

    Classes with the fewest candidates are resolved first (least freedom), and
    within a class we pick the task with the highest marginal coverage gain,
    tie-broken toward harder (lower reach-rate) tasks then by dir name.
    """
    by_class: dict[str, list[TaskFeat]] = {}
    for f in feats:
        by_class.setdefault(f.metaclass, []).append(f)
    if len(by_class) != k:
        # Not fatal, but the "one per class" identity no longer holds; be loud.
        print(
            f"[warn] {len(by_class)} scenario classes but k={k}; "
            "selecting one per class (result size == #classes).",
            file=sys.stderr,
        )

    # Inverse global frequency -> rarity weight per method (PUT >> GET >> POST).
    method_freq = Counter(f.method for f in feats)
    total = len(feats)

    seen_platforms: set[str] = set()
    seen_methods: Counter[str] = Counter()
    seen_bands: Counter[str] = Counter()
    graphql_taken = 0

    def gain(f: TaskFeat) -> tuple:
        platform_new = f.platform not in seen_platforms
        method_rarity = total / method_freq[f.method]  # POST~1.1, GET~13, PUT~130
        band_deficit = 1.0 / (1 + seen_bands[f.reach_band])
        graphql_bonus = 2.0 if (f.is_graphql and graphql_taken == 0) else 0.0
        score = (
            3.0 * platform_new
            + 1.5 * method_rarity
            + 1.0 * band_deficit
            + graphql_bonus
        )
        # Tie-break: higher score, then harder (lower reach_rate), then stable name.
        return (score, -f.reach_rate, _neg_str(f.task_dir))

    chosen: list[TaskFeat] = []
    for metaclass in sorted(by_class, key=lambda c: (len(by_class[c]), c)):
        best = max(by_class[metaclass], key=gain)
        chosen.append(best)
        seen_platforms.add(best.platform)
        seen_methods[best.method] += 1
        seen_bands[best.reach_band] += 1
        graphql_taken += int(best.is_graphql)

    return sorted(chosen, key=lambda f: f.task_id)


def _neg_str(s: str) -> tuple:
    # Make "smaller name wins" work inside a max() by negating the ordering.
    return tuple(-ord(c) for c in s)


def coverage_report(all_feats: list[TaskFeat], lite: list[TaskFeat]) -> dict[str, Any]:
    def dist(feats: list[TaskFeat], attr: str) -> dict[str, int]:
        return dict(Counter(getattr(f, attr) for f in feats).most_common())

    return {
        "n_full": len(all_feats),
        "n_lite": len(lite),
        "scenario_classes": {
            "full": len({f.metaclass for f in all_feats}),
            "lite": len({f.metaclass for f in lite}),
        },
        "platforms": {"full": len({f.platform for f in all_feats}), "lite": len({f.platform for f in lite})},
        "methods": {"full": dist(all_feats, "method"), "lite": dist(lite, "method")},
        "graphql": {"full": sum(f.is_graphql for f in all_feats), "lite": sum(f.is_graphql for f in lite)},
        "reach_band": {"full": dist(all_feats, "reach_band"), "lite": dist(lite, "reach_band")},
        "exec_mode_provisional": {"lite": dist(lite, "exec_mode_provisional")},
    }


def build_manifest(lite: list[TaskFeat], coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "CLAWBENCH-LITE",
        "selector_version": SELECTOR_VERSION,
        "generated_from": "test-cases/v2",
        "k": len(lite),
        "note": (
            "One representative per scenario class (metaclass), chosen to preserve "
            "platform / outcome-method / pilot-failure-regime coverage. Deterministic."
        ),
        "coverage": coverage,
        "tasks": [
            {
                "task_dir": f.task_dir,
                "task_id": f.task_id,
                "metaclass": f.metaclass,
                "class": f.cls,
                "platform": f.platform,
                "method": f.method,
                "is_graphql": f.is_graphql,
                "reach_rate": round(f.reach_rate, 4),
                "reach_band": f.reach_band,
                "dominant_pilot_failure": f.dominant_fail_cat,
                "exec_mode_provisional": f.exec_mode_provisional,
            }
            for f in lite
        ],
    }


def _render_coverage(cov: dict[str, Any]) -> str:
    return (
        "CLAWBENCH-LITE coverage\n"
        "=======================\n"
        f"  tasks            : {cov['n_lite']} / {cov['n_full']}\n"
        f"  scenario classes : {cov['scenario_classes']['lite']} / {cov['scenario_classes']['full']}\n"
        f"  platforms        : {cov['platforms']['lite']} / {cov['platforms']['full']}\n"
        f"  methods (lite)   : {cov['methods']['lite']}\n"
        f"  graphql          : {cov['graphql']['lite']} / {cov['graphql']['full']}\n"
        f"  reach band (lite): {cov['reach_band']['lite']}\n"
        f"  exec mode (prov.): {cov['exec_mode_provisional']['lite']}\n"
    )


def materialise(lite: list[TaskFeat], manifest: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in lite:
        src = TASKS_V2 / f.task_dir
        dst = out_dir / f.task_dir
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
    (out_dir / "lite_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Select the CLAWBENCH-LITE 30-task subset.")
    ap.add_argument("--write", action="store_true", help="materialise test-cases/v2-lite/")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output dir for the LITE subset")
    ap.add_argument("--check", action="store_true", help="fail (exit 1) if any axis under-covered")
    ap.add_argument("--json", action="store_true", help="print the manifest JSON")
    args = ap.parse_args(argv)

    feats = load_features()
    lite = select_lite(feats)
    cov = coverage_report(feats, lite)
    manifest = build_manifest(lite, cov)

    print(_render_coverage(cov), file=sys.stderr)
    if args.json:
        print(json.dumps(manifest, indent=2))

    if args.write:
        materialise(lite, manifest, args.out)
        print(f"[ok] wrote {len(lite)} tasks + lite_manifest.json to {args.out}", file=sys.stderr)

    if args.check:
        problems = []
        if cov["scenario_classes"]["lite"] != cov["scenario_classes"]["full"]:
            problems.append("not every scenario class represented")
        if {"POST", "GET", "PUT"} - set(cov["methods"]["lite"]):
            problems.append(f"missing outcome method(s): {sorted({'POST','GET','PUT'} - set(cov['methods']['lite']))}")
        if cov["graphql"]["lite"] == 0:
            problems.append("no GraphQL-constraint task in LITE")
        if len(cov["reach_band"]["lite"]) < 3:
            problems.append(f"reach-band coverage thin: {cov['reach_band']['lite']}")
        if problems:
            for p in problems:
                print(f"[check] FAIL: {p}", file=sys.stderr)
            return 1
        print("[check] OK: all axes covered", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
