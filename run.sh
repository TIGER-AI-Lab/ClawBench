#!/bin/bash
cd "$(dirname "$0")" || exit
exec uv run --project test-driver test-driver/tui.py
