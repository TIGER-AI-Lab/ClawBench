"""``clawbench-sources`` — inspect the registered task-source adapters."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from clawbench.adapters._base import (
    AdapterError,
    get_adapter,
    offline,
    parse_source_spec,
    registered_sources,
)


def _status_row(name: str, path: Path | None) -> dict[str, Any]:
    status = get_adapter(name).status(path)
    return {
        "name": status.name,
        "upstream": status.upstream,
        "pinned_sha": status.pinned_sha,
        "scoring_layers": [layer.value for layer in status.scoring_layers],
        "path": str(status.cache_dir),
        "state": (
            "bundled" if status.bundled else ("cached" if status.cached else "missing")
        ),
    }


def _print_table(rows: list[dict[str, Any]]) -> None:
    headers = ("SOURCE", "STATE", "UPSTREAM", "PIN", "PATH")
    table = [
        (
            row["name"],
            row["state"],
            row["upstream"] or "-",
            (row["pinned_sha"] or "-")[:12],
            row["path"],
        )
        for row in rows
    ]
    widths = [
        max(len(header), *(len(cell[i]) for cell in table)) if table else len(header)
        for i, header in enumerate(headers)
    ]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip())
    for cell in table:
        print("  ".join(c.ljust(w) for c, w in zip(cell, widths)).rstrip())


def _cmd_list(args: argparse.Namespace) -> int:
    rows = [_status_row(name, None) for name in registered_sources()]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        _print_table(rows)
        if offline():
            print("\nCLAWBENCH_OFFLINE is set; missing sources will not be fetched.")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    name, path = parse_source_spec(args.source)
    adapter = get_adapter(name)
    row = _status_row(name, path)
    if args.json:
        print(json.dumps(row, indent=2))
        return 0
    print(f"{row['name']}  ({row['state']})")
    print(f"  upstream:       {row['upstream'] or '-'}")
    print(f"  pinned commit:  {row['pinned_sha'] or '-'}")
    print(f"  scoring layers: {', '.join(row['scoring_layers']) or '-'}")
    print(f"  path:           {row['path']}")
    doc = sys.modules[adapter.__class__.__module__].__doc__ or ""
    if doc.strip():
        print()
        print(doc.strip())
    return 0


def _cmd_cases(args: argparse.Namespace) -> int:
    name, spec_path = parse_source_spec(args.source)
    adapter = get_adapter(name)
    path = args.path or spec_path or adapter.default_path()
    tasks = adapter.load(Path(path))
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "task_id": task.task_id,
                        "source": task.source,
                        "source_id": task.source_id,
                        "category": task.category,
                        "time_limit": task.time_limit,
                        "scoring_layers": [
                            layer.value for layer in task.scoring_layers
                        ],
                        "warnings": [str(w) for w in task.warnings],
                    }
                    for task in tasks
                ],
                indent=2,
            )
        )
        return 0
    for task in tasks:
        print(task.task_id)
        for warning in task.warnings:
            print(f"  ! {warning}")
    print(f"\n{len(tasks)} task(s) from {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clawbench-sources",
        description="Inspect the registered ClawBench task-source adapters.",
    )
    # With no subcommand, `clawbench-sources` behaves as `... list`.
    parser.set_defaults(command="list", func=_cmd_list, json=False)
    subparsers = parser.add_subparsers(dest="command")

    list_parser = subparsers.add_parser("list", help="list registered sources")
    list_parser.add_argument("--json", action="store_true", help="emit JSON")
    list_parser.set_defaults(func=_cmd_list)

    show_parser = subparsers.add_parser(
        "show", help="show one source's status and field mapping"
    )
    show_parser.add_argument("source", help="source name, or name:/path/to/checkout")
    show_parser.add_argument("--json", action="store_true", help="emit JSON")
    show_parser.set_defaults(func=_cmd_show)

    cases_parser = subparsers.add_parser(
        "cases", help="list the tasks a source can import"
    )
    cases_parser.add_argument("source", help="source name, or name:/path/to/checkout")
    cases_parser.add_argument(
        "--path",
        type=Path,
        help="checkout to read instead of the source's default location",
    )
    cases_parser.add_argument("--json", action="store_true", help="emit JSON")
    cases_parser.set_defaults(func=_cmd_cases)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except AdapterError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
