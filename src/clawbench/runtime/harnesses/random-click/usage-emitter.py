#!/usr/bin/env python3
"""Random-click harness usage emitter: no model calls → empty usage."""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    Path("/data/usage.jsonl").write_text("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
