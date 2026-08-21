"""Crash-safe JSON writes and tolerant JSON reads for run metadata."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, data: Any, *, indent: int = 2) -> None:
    """Write ``data`` to ``path`` so readers never observe a partial file.

    The payload lands in a temporary file alongside the target, is flushed all
    the way to disk, and is then moved into place with :func:`os.replace`, which
    replaces atomically on POSIX and Windows alike. A crash mid-write therefore
    leaves either the previous file or no file, never a truncated one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=indent)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_json_or_none(path: Path) -> Any | None:
    """Return the parsed contents of ``path``, or ``None`` if it cannot be read.

    Batch reporting walks run directories produced by other processes, any of
    which may have been killed mid-write by the host or by an older ClawBench.
    A single unreadable file must not abort reporting for the whole batch.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
