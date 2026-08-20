"""Configuration and path helpers for single ClawBench runs."""

import os
import shutil
import sys
from pathlib import Path

from clawbench.runner.run_support.harness_registry import (
    HARNESS_REGISTRY,
    HARNESS_REGISTRY_YAML,
    HarnessRegistry,
    load_harness_registry,
)
from clawbench.utils.model_config import (
    MODELS_YAML,
    ModelConfigError,
    load_model_config,
    load_models_yaml,
)
from clawbench.utils.paths import (
    ASSET_ROOT,
    WORKSPACE_ROOT,
    bundled_path,
    workspace_path,
)

__all__ = [
    "ASSET_ROOT",
    "BASE_IMAGE",
    "DEFAULT_HARNESS",
    "ENGINE",
    "HARNESS_REGISTRY",
    "HARNESS_REGISTRY_YAML",
    "HARNESSES",
    "IMAGE",
    "MODELS_YAML",
    "WORKSPACE_ROOT",
    "HarnessRegistry",
    "ModelConfigError",
    "harness_image",
    "load_dotenv",
    "load_harness_registry",
    "load_model_config",
    "load_models_yaml",
    "load_runtime_env",
    "resolve_task_file",
    "resolve_test_case_dir",
    "resolve_test_case_path",
]

HARNESSES = HARNESS_REGISTRY.harnesses
DEFAULT_HARNESS = HARNESS_REGISTRY.default
BASE_IMAGE = HARNESS_REGISTRY.base_image


def harness_image(harness: str) -> str:
    """Return the docker image tag for a given harness name."""
    try:
        return HARNESS_REGISTRY.harness_images[harness]
    except KeyError as e:
        raise ValueError(
            f"Unknown harness {harness!r}; expected one of {list(HARNESSES)}"
        ) from e


# Kept for back-compat with old callers / scripts that imported IMAGE.
IMAGE = harness_image(DEFAULT_HARNESS)


def _detect_engine() -> str:
    # Help output is host-only and should work on machines that have not
    # installed Docker/Podman yet. Actual run paths still call this without
    # help flags and fail fast if no engine is available.
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        env = os.environ.get("CONTAINER_ENGINE", "").strip().lower()
        return env if env in ("docker", "podman") else "docker"

    env = os.environ.get("CONTAINER_ENGINE", "").strip().lower()
    if env:
        if env not in ("docker", "podman"):
            print(f"ERROR: CONTAINER_ENGINE must be 'docker' or 'podman', got '{env}'")
            sys.exit(1)
        if not shutil.which(env):
            print(f"ERROR: CONTAINER_ENGINE={env} but '{env}' not found on PATH")
            sys.exit(1)
        return env
    for cmd in ("docker", "podman"):
        if shutil.which(cmd):
            return cmd
    print("ERROR: Neither 'podman' nor 'docker' found on PATH")
    sys.exit(1)


ENGINE = _detect_engine()


def load_dotenv(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_runtime_env() -> dict[str, str]:
    """Load runtime credentials in increasing precedence order."""
    env = load_dotenv(bundled_path(".env"))
    env.update(load_dotenv(workspace_path(".env")))
    env.update(load_dotenv(workspace_path(".env.local")))
    env.update(os.environ)
    return env


def resolve_test_case_path(path: Path) -> Path:
    """Resolve a case directory or task JSON path from cwd/workspace first, then bundled assets."""
    if path.is_absolute():
        return path
    candidates = [
        Path.cwd() / path,
        WORKSPACE_ROOT / path,
        ASSET_ROOT / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return (Path.cwd() / path).resolve()


def resolve_test_case_dir(path: Path) -> Path:
    """Resolve a case directory from cwd/workspace first, then bundled assets."""
    resolved = resolve_test_case_path(path)
    return resolved.parent if resolved.is_file() else resolved


def resolve_task_file(path: Path) -> tuple[Path, Path, str]:
    """Return (task_dir, task_file, case_name) for directory or flat task JSON input."""
    resolved = resolve_test_case_path(path)
    if resolved.is_file():
        return resolved.parent, resolved, resolved.stem
    return resolved, resolved / "task.json", resolved.name
