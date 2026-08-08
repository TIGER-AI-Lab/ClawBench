"""Script to update and validate llms.txt dynamically against CITATION.cff."""

import argparse
import sys
from pathlib import Path
import yaml

from clawbench.utils.paths import ASSET_ROOT, WORKSPACE_ROOT


def get_bibtex(cff_path: Path | None = None) -> str:
    """Parse CITATION.cff and format BibTeX string."""
    if cff_path is None:
        cff_path = (
            WORKSPACE_ROOT / "CITATION.cff"
            if (WORKSPACE_ROOT / "CITATION.cff").exists()
            else ASSET_ROOT / "CITATION.cff"
        )
    if not cff_path.exists():
        return ""

    with open(cff_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    pref = data.get("preferred-citation", {})
    authors_raw = pref.get("authors", data.get("authors", []))
    authors = [
        f"{a['family-names']}, {a['given-names']}"
        for a in authors_raw
        if "family-names" in a and "given-names" in a
    ]

    title = pref.get("title", data.get("title", ""))
    journal = pref.get("journal", "")
    year = pref.get("year", 2026)

    return (
        f"@article{{zhang2026clawbench,\n"
        f"  title={{{title}}},\n"
        f"  author={{{' and '.join(authors)}}},\n"
        f"  journal={{{journal}}},\n"
        f"  year={{{year}}}\n"
        f"}}"
    )


def generate_llms_txt_content() -> str:
    """Generate exact llms.txt Markdown content with BibTeX from CITATION.cff."""
    bibtex = get_bibtex()
    return f"""# ClawBench

> ClawBench is an open-source benchmark for evaluating browser and computer-use agents on everyday tasks performed on live websites.

ClawBench measures end-to-end task success while preserving replayable evidence from browser actions, screenshots, network requests, agent messages, and session recordings. The benchmark blocks only the final side-effecting submission request so tasks can run on real websites without completing purchases, bookings, or applications.

## Canonical resources

- [Project page](https://claw-bench.com): overview, task explorer, leaderboard, and evaluation details.
- [GitHub repository](https://github.com/reacher-z/ClawBench): source code, task definitions, harnesses, and documentation.
- [Research paper](https://arxiv.org/abs/2604.08523): *ClawBench: Can AI Agents Complete Everyday Online Tasks?*
- [Citation metadata](https://github.com/reacher-z/ClawBench/blob/main/CITATION.cff): machine-readable citation record.
- [Task and leaderboard Space](https://huggingface.co/spaces/TIGER-Lab/ClawBench): live evaluation results and task explorer.
- [Task dataset](https://huggingface.co/datasets/NAIL-Group/ClawBench): V1/V2 task definitions and evaluation metadata.
- [V1 execution traces](https://huggingface.co/datasets/NAIL-Group/ClawBenchV1Trace): replayable run artifacts.
- [V2 execution traces](https://huggingface.co/datasets/TIGER-Lab/ClawBenchV2Trace): rolling V2 run artifacts.

## Quick facts

- V1: 153 tasks across 144 live websites and 15 life categories.
- V2: 130 tasks with six first-class agent harnesses.
- Evidence layers: session replay, screenshots, HTTP traffic, browser actions, and agent messages.
- Supported harnesses include OpenClaw, OpenCode, Claude Code, Codex, Browser-Use, Hermes, Pi, and other compatible browser agents.

## Citations 
```bibtex
{bibtex}
```
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Update or check llms.txt.")
    parser.add_argument("--output", "-o", type=Path, default=WORKSPACE_ROOT / "llms.txt")
    parser.add_argument("--check", action="store_true", help="Check sync status.")
    parser.add_argument("--dry-run", action="store_true", help="Print content.")
    args = parser.parse_args()

    content = generate_llms_txt_content()
    if args.dry_run:
        print(content)
        return
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8").strip() != content.strip():
            print(f"FAILED: {args.output} is out of sync.", file=sys.stderr)
            sys.exit(1)
        print(f"SUCCESS: {args.output} is in sync.")
        return

    args.output.write_text(content, encoding="utf-8")
    print(f"Successfully updated {args.output}")


if __name__ == "__main__":
    main()
