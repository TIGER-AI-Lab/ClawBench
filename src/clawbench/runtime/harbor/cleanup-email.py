#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

PURELYMAIL_API = "https://purelymail.com/api/v0"


def env_value(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip().strip('"').strip("'")
    return ""


def purelymail_request(endpoint: str, body: dict, api_key: str) -> dict:
    data = json.dumps(body).encode()
    req = Request(
        f"{PURELYMAIL_API}/{endpoint}",
        data=data,
        headers={"Purelymail-Api-Token": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean up ClawBench Harbor email")
    parser.add_argument(
        "--state-file", type=Path, default=Path("/data/harbor-task-state.json")
    )
    args = parser.parse_args()
    if not args.state_file.exists():
        return 0
    api_key = env_value("PURELY_MAIL_API_KEY", "PURELYMAIL_API_KEY")
    if not api_key:
        return 0
    try:
        state = json.loads(args.state_file.read_text())
        email = state.get("email")
        if email:
            purelymail_request("deleteUser", {"userName": email}, api_key)
    except (OSError, json.JSONDecodeError, URLError, Exception) as exc:
        print(f"WARNING: failed to clean up PurelyMail account: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
