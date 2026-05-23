"""Configuration and path helpers for single ClawBench runs."""

import os
import shutil
import sys
from pathlib import Path

import yaml

from clawbench.runner.run_support.harness_registry import (
    HARNESS_REGISTRY,
    HARNESS_REGISTRY_YAML,
    HarnessRegistry,
    load_harness_registry,
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
MODELS_YAML = WORKSPACE_ROOT / "models" / "models.yaml"


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


def load_models_yaml() -> dict:
    """Load all model definitions from models/models.yaml."""
    if not MODELS_YAML.exists():
        print(
            f"ERROR: {MODELS_YAML} not found (copy models.example.yaml and fill in your keys)"
        )
        sys.exit(1)
    return yaml.safe_load(MODELS_YAML.read_text()) or {}


def load_runtime_env() -> dict[str, str]:
    """Load runtime credentials, preferring workspace overrides."""
    env = load_dotenv(bundled_path(".env"))
    env.update(load_dotenv(workspace_path(".env")))
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


def load_model_config(model: str) -> dict:
    """Load a model config by name from models/models.yaml.

    The YAML key is the model name (passed as MODEL_NAME to the container).
    """
    all_models = load_models_yaml()
    if model not in all_models:
        print(f"ERROR: model '{model}' not found in {MODELS_YAML}")
        print(f"Available models: {', '.join(sorted(all_models))}")
        sys.exit(1)

    # Validate model name characters. Note: '/' and ':' are valid in
    # vendor-prefixed ids like 'anthropic/claude-sonnet-4-6' or
    # 'arcee-ai/trinity-large-preview:free' — they get sanitized to
    # '--' before being used as path components. We only reject characters
    # that could cause real trouble in shell/filesystem paths even after
    # that sanitization.
    bad = [c for c in ' \\*?"<>|' if c in model]
    if bad:
        print(
            f"ERROR: model name '{model}' contains illegal character(s): "
            f"{' '.join(repr(c) for c in bad)}"
        )
        sys.exit(1)

    config = dict(all_models[model])
    config["model"] = model  # the YAML key IS the model name

    required = ["base_url", "api_type"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        for k in missing:
            print(f"ERROR: Required field '{k}' missing for model '{model}'")
        sys.exit(1)

    # Normalize API keys: api_keys list wins, else wrap api_key into list.
    if config.get("api_keys"):
        config["api_key"] = config["api_keys"][0]
    elif config.get("api_key"):
        config["api_keys"] = [config["api_key"]]

    if not config.get("api_keys"):
        print(f"ERROR: no api_key or api_keys for model '{model}'")
        sys.exit(1)

    return config
