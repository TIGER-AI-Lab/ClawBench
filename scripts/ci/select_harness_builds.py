"""Select native harness builds from changed paths; emit GitHub Actions outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath

RUNTIME_ROOT = Path("src/clawbench/runtime")


def select_dockerfiles(
    runtime_root: Path, changed_paths: list[str] | None
) -> list[Path]:
    """None requests all builds; shared runtime dependencies affect every harness."""
    harness_root = runtime_root / "harnesses"
    available = sorted(
        p
        for p in harness_root.glob("*/Dockerfile*")
        if p.is_file() and p.parent.name != "base"
    )
    runtime_prefix = PurePosixPath(runtime_root.as_posix())
    relative_paths = []
    for path in changed_paths or []:
        try:
            relative_paths.append(PurePosixPath(path).relative_to(runtime_prefix))
        except ValueError:
            continue
    # A workflow/selector-only change should exercise the full build plan too.
    if changed_paths is None or not relative_paths:
        return available

    shared = {"runtime-server", "chrome-extension", "shared"}
    affected = set()
    for path in relative_paths:
        if not path.parts:
            continue
        if path.parts[0] in shared:
            return available
        if path.parts[0] == "harnesses" and len(path.parts) >= 2:
            harness = path.parts[1]
            if harness in {"base", "harnesses.yaml", "harness.schema.json"}:
                return available
            affected.add(harness)
    return [p for p in available if p.parent.name in affected]


def build_matrix(dockerfiles: list[Path]) -> dict[str, list[dict[str, str]]]:
    return {
        "include": [
            {
                "harness": p.parent.name,
                "dockerfile": p.as_posix(),
                "image": f"clawbench-{p.parent.name}",
            }
            for p in dockerfiles
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--all", action="store_true")
    source.add_argument(
        "--changed-files", type=Path, help="NUL-delimited git diff paths"
    )
    parser.add_argument("--runtime-root", type=Path, default=RUNTIME_ROOT)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--github-summary", type=Path)
    args = parser.parse_args()
    changed = (
        None
        if args.all
        else [p for p in args.changed_files.read_bytes().decode().split("\0") if p]
    )
    selected = select_dockerfiles(args.runtime_root, changed)
    matrix = json.dumps(build_matrix(selected), separators=(",", ":"))
    if args.github_output:
        with args.github_output.open("a") as output:
            output.write(f"matrix={matrix}\ncount={len(selected)}\n")
    if args.github_summary:
        with args.github_summary.open("a") as summary:
            summary.write(
                "## Harness build plan\n\n"
                f"Selected {len(selected)} native harness images. "
                "The base image is built separately.\n\n"
                "| Image | Dockerfile |\n| --- | --- |\n"
            )
            for row in build_matrix(selected)["include"]:
                summary.write(f"| `{row['image']}` | `{row['dockerfile']}` |\n")
    print(matrix)


if __name__ == "__main__":
    main()
