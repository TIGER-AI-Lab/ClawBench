"""Tests for the generalization-split builder (scripts/build_splits.py).

The split invariants (disjoint + complete partitions, no leakage-group
straddle, family-observed / family-absent guarantees) are correctness
properties of a released benchmark, so we assert them directly, plus
determinism and the outcome-host parser.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_splits as bs  # noqa: E402


def test_outcome_host_from_regex_pattern() -> None:
    assert bs._outcome_host(r"www\.idealist\.org/data/userdashboard") == "idealist.org"
    assert bs._outcome_host(r"taskrabbit\.com/(api/v\d+/jobs)") == "taskrabbit.com"
    assert bs._outcome_host(r"habitica\.com/api/v\d+/tasks/user") == "habitica.com"
    assert bs._outcome_host("") == ""


def test_splits_pass_all_invariants() -> None:
    tasks = bs.load_tasks()
    spec = bs.build_splits(tasks)
    assert bs.check_invariants(tasks, spec) == []


def test_splits_are_deterministic() -> None:
    tasks = bs.load_tasks()
    a = bs.build_splits(tasks)
    b = bs.build_splits(tasks)
    assert a == b


def test_website_level_splits_are_full_partitions() -> None:
    tasks = bs.load_tasks()
    spec = bs.build_splits(tasks)
    all_dirs = {t["task_dir"] for t in tasks}
    for name in ("held_out_task", "held_out_website", "held_out_website_and_action"):
        s = spec["splits"][name]
        tr, ev = set(s["train"]), set(s["eval"])
        assert tr.isdisjoint(ev)
        assert tr | ev == all_dirs
        assert ev, f"{name} has empty eval"


def test_held_out_website_keeps_family_in_train() -> None:
    tasks = bs.load_tasks()
    spec = bs.build_splits(tasks)
    by_dir = {t["task_dir"]: t for t in tasks}
    s = spec["splits"]["held_out_website"]
    train_families = {by_dir[d]["metaclass"] for d in s["train"]}
    eval_families = {by_dir[d]["metaclass"] for d in s["eval"]}
    assert eval_families <= train_families


def test_held_out_website_and_action_removes_family_from_train() -> None:
    tasks = bs.load_tasks()
    spec = bs.build_splits(tasks)
    by_dir = {t["task_dir"]: t for t in tasks}
    s = spec["splits"]["held_out_website_and_action"]
    train_families = {by_dir[d]["metaclass"] for d in s["train"]}
    eval_families = {by_dir[d]["metaclass"] for d in s["eval"]}
    assert train_families.isdisjoint(eval_families)


def test_check_gate_passes() -> None:
    assert bs.main(["--check"]) == 0
