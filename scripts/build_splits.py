#!/usr/bin/env python3
"""Build CLAWBENCH v2 train / evaluation generalization splits.

The proposal (Appendix C) defines four generalization settings. Each is a
*separate* partition of the 130 tasks answering a different question:

  1. held_out_task              -- website seen in training, this task held out.
                                   Measures within-site generalization.
  2. held_out_website           -- whole website held out, but its action
                                   family (metaclass) is seen on other sites.
                                   Measures transfer across interfaces.
  3. held_out_website_and_action-- website AND action family both absent from
                                   training. The strongest setting.
  4. repeated_in_distribution   -- a training-compatible subset flagged for
                                   repeated rollouts (variance / overfitting).

To prevent leakage we group tasks that share an outcome host (registrable
domain of the eval_schema URL) or platform; a leakage group is never split
across train/eval in the *website-level* settings (2 and 3). Setting 1 shares
the website by design, so the group constraint does not apply there.

Fully deterministic: sorted iteration, fixed hold-out rules, no randomness.

Usage::

    python scripts/build_splits.py --check          # validate invariants only
    python scripts/build_splits.py --write          # write test-cases/splits/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TASKS_V2 = REPO_ROOT / "test-cases" / "v2"
DEFAULT_OUT = REPO_ROOT / "test-cases" / "splits"

POLICY_VERSION = "1.0.0"
REPEAT_COUNT = 3
REPEAT_SUBSET_SIZE = 10

_DOMAIN_RE = re.compile(r"([a-z0-9-]+(?:\\?\.[a-z0-9-]+)+)", re.IGNORECASE)


def _outcome_host(url_pattern: str) -> str:
    """Best-effort registrable domain from a (regex) URL pattern."""
    if not url_pattern:
        return ""
    m = _DOMAIN_RE.search(url_pattern)
    if not m:
        return ""
    host = m.group(1).replace("\\", "").lower().lstrip(".")
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 2:
        return ".".join(parts[-2:])  # e.g. www.idealist.org -> idealist.org
    return host


def load_tasks() -> list[dict[str, Any]]:
    tasks = []
    for p in sorted(d for d in TASKS_V2.iterdir() if d.is_dir()):
        tj = p / "task.json"
        if not tj.is_file():
            continue
        d = json.loads(tj.read_text())
        meta = d.get("metadata", {})
        es = d.get("eval_schema", {}) or {}
        tasks.append(
            {
                "task_dir": p.name,
                "task_id": int(meta.get("task_id", -1)),
                "metaclass": str(meta.get("metaclass", "unknown")),
                "platform": str(meta.get("platform", "unknown")),
                "method": str(es.get("method", "UNKNOWN")).upper(),
                "host": _outcome_host(str(es.get("url_pattern", ""))) or str(meta.get("platform", "")),
            }
        )
    return tasks


def _leakage_groups(tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group tasks that must stay together: same outcome host (or platform)."""
    groups: dict[str, list[str]] = defaultdict(list)
    for t in tasks:
        key = t["host"] or t["platform"]
        groups[key].append(t["task_dir"])
    return {k: sorted(v) for k, v in sorted(groups.items())}


def _by(tasks: list[dict[str, Any]], attr: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in tasks:
        out[t[attr]].append(t)
    return {k: sorted(v, key=lambda x: x["task_id"]) for k, v in sorted(out.items())}


def split_held_out_task(tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Websites with >=2 tasks: hold out the highest-task_id one to eval."""
    by_platform = _by(tasks, "platform")
    eval_dirs, train_dirs = [], []
    for _, group in by_platform.items():
        if len(group) >= 2:
            eval_dirs.append(group[-1]["task_dir"])
            train_dirs.extend(t["task_dir"] for t in group[:-1])
        else:
            train_dirs.extend(t["task_dir"] for t in group)
    return {"train": sorted(train_dirs), "eval": sorted(eval_dirs)}


def split_held_out_website(tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Hold out whole websites whose action family is still seen in training.

    Greedily accept a platform for eval only if, after removing *all* its tasks
    (a platform can appear under several families), every action family still
    keeps at least one training task -- so each held-out website's family is
    guaranteed to remain observed in training.
    """
    all_metaclasses = {t["metaclass"] for t in tasks}
    # Candidates: top-by-name platform of each family that spans >=2 platforms.
    candidates: set[str] = set()
    for _, group in _by(tasks, "metaclass").items():
        platforms = sorted({t["platform"] for t in group})
        if len(platforms) >= 2:
            candidates.add(platforms[-1])

    eval_platforms: set[str] = set()
    for platform in sorted(candidates):
        trial = eval_platforms | {platform}
        surviving = {t["metaclass"] for t in tasks if t["platform"] not in trial}
        if surviving == all_metaclasses:
            eval_platforms = trial

    eval_dirs = sorted(t["task_dir"] for t in tasks if t["platform"] in eval_platforms)
    train_dirs = sorted(t["task_dir"] for t in tasks if t["platform"] not in eval_platforms)
    return {"train": train_dirs, "eval": eval_dirs, "eval_platforms": sorted(eval_platforms)}


def split_held_out_website_and_action(tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Hold out whole action families whose websites are exclusive to them.

    A family is eligible only if none of its outcome hosts are shared with
    another family; that makes holding the family out also hold its websites
    out, with no leakage-group straddle. Smallest eligible families first.
    """
    host_families: dict[str, set[str]] = defaultdict(set)
    for t in tasks:
        host_families[t["host"]].add(t["metaclass"])

    by_metaclass = _by(tasks, "metaclass")
    eligible = {
        mc: group
        for mc, group in by_metaclass.items()
        if all(len(host_families[t["host"]]) == 1 for t in group)
    }
    target = min(max(1, round(0.15 * len(by_metaclass))), len(eligible))
    ranked = sorted(eligible.items(), key=lambda kv: (len(kv[1]), kv[0]))
    eval_metaclasses = {mc for mc, _ in ranked[:target]}

    eval_dirs = sorted(t["task_dir"] for t in tasks if t["metaclass"] in eval_metaclasses)
    train_dirs = sorted(t["task_dir"] for t in tasks if t["metaclass"] not in eval_metaclasses)
    return {"train": train_dirs, "eval": eval_dirs, "eval_metaclasses": sorted(eval_metaclasses)}


def split_repeated_in_distribution(train_dirs: list[str]) -> dict[str, Any]:
    """Flag a deterministic training subset for repeated rollouts."""
    subset = sorted(train_dirs)[:REPEAT_SUBSET_SIZE]
    return {"tasks": subset, "n_repeats": REPEAT_COUNT}


def build_splits(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    s1 = split_held_out_task(tasks)
    s2 = split_held_out_website(tasks)
    s3 = split_held_out_website_and_action(tasks)
    s4 = split_repeated_in_distribution(s3["train"])
    return {
        "policy_version": POLICY_VERSION,
        "n_tasks": len(tasks),
        "leakage_groups": _leakage_groups(tasks),
        "splits": {
            "held_out_task": s1,
            "held_out_website": s2,
            "held_out_website_and_action": s3,
            "repeated_in_distribution": s4,
        },
    }


def check_invariants(tasks: list[dict[str, Any]], spec: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    by_dir = {t["task_dir"]: t for t in tasks}
    groups = spec["leakage_groups"]
    dir_to_group = {d: g for g, ds in groups.items() for d in ds}
    splits = spec["splits"]

    def _partitions(name: str) -> tuple[set[str], set[str]]:
        s = splits[name]
        return set(s["train"]), set(s["eval"])

    # Every website-level split must be a full, disjoint partition of the pool.
    for name in ("held_out_task", "held_out_website", "held_out_website_and_action"):
        tr, ev = _partitions(name)
        if tr & ev:
            problems.append(f"{name}: train/eval overlap ({len(tr & ev)} tasks)")
        if tr | ev != set(by_dir):
            problems.append(f"{name}: does not cover all {len(by_dir)} tasks")
        if not ev:
            problems.append(f"{name}: empty eval set")

    # Leakage: no leakage group may straddle train/eval in website-level splits.
    for name in ("held_out_website", "held_out_website_and_action"):
        tr, ev = _partitions(name)
        straddlers = {
            dir_to_group[d]
            for d in ev
            if any((o in tr) for o in groups[dir_to_group[d]])
        }
        if straddlers:
            problems.append(f"{name}: leakage groups straddle train/eval: {sorted(straddlers)[:5]}")

    # held_out_website: each eval platform's family must survive in training.
    tr2, ev2 = _partitions("held_out_website")
    train_families = {by_dir[d]["metaclass"] for d in tr2}
    for d in ev2:
        if by_dir[d]["metaclass"] not in train_families:
            problems.append(
                f"held_out_website: eval family {by_dir[d]['metaclass']!r} absent from train"
            )
            break

    # held_out_website_and_action: eval families must be ABSENT from training.
    tr3, ev3 = _partitions("held_out_website_and_action")
    train_families3 = {by_dir[d]["metaclass"] for d in tr3}
    leaked = {by_dir[d]["metaclass"] for d in ev3} & train_families3
    if leaked:
        problems.append(f"held_out_website_and_action: families leak into train: {sorted(leaked)}")

    return problems


def _render(spec: dict[str, Any]) -> str:
    s = spec["splits"]
    return (
        "CLAWBENCH v2 generalization splits\n"
        "==================================\n"
        f"  tasks                        : {spec['n_tasks']}\n"
        f"  leakage groups               : {len(spec['leakage_groups'])}\n"
        f"  held_out_task                : {len(s['held_out_task']['train'])} train / "
        f"{len(s['held_out_task']['eval'])} eval\n"
        f"  held_out_website             : {len(s['held_out_website']['train'])} train / "
        f"{len(s['held_out_website']['eval'])} eval "
        f"({len(s['held_out_website']['eval_platforms'])} websites)\n"
        f"  held_out_website_and_action  : {len(s['held_out_website_and_action']['train'])} train / "
        f"{len(s['held_out_website_and_action']['eval'])} eval "
        f"(families: {', '.join(s['held_out_website_and_action']['eval_metaclasses'])})\n"
        f"  repeated_in_distribution     : {len(s['repeated_in_distribution']['tasks'])} tasks "
        f"x{s['repeated_in_distribution']['n_repeats']}\n"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build CLAWBENCH v2 generalization splits.")
    ap.add_argument("--write", action="store_true", help="write test-cases/splits/splits.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="fail (exit 1) on any invariant violation")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    tasks = load_tasks()
    spec = build_splits(tasks)
    print(_render(spec), file=sys.stderr)
    if args.json:
        print(json.dumps(spec, indent=2))

    if args.write:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "splits.json").write_text(json.dumps(spec, indent=2) + "\n")
        print(f"[ok] wrote splits.json to {args.out}", file=sys.stderr)

    problems = check_invariants(tasks, spec)
    if problems:
        for p in problems:
            print(f"[check] FAIL: {p}", file=sys.stderr)
        return 1 if args.check else 0
    print("[check] OK: splits are disjoint, complete, and leakage-free", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
