#!/usr/bin/env python3
"""Ensure the usage artifact written by the WebBrain driver exists."""

from pathlib import Path


def main() -> int:
    Path("/data/usage.jsonl").touch(exist_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
