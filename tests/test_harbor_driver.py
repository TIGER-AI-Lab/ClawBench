"""Tests for the in-container Harbor driver (runtime/harnesses/harbor/harbor_driver.py).

The driver runs inside a minimal Harbor venv that has *only* ``harbor`` installed
(see Dockerfile.harbor), so ``clawbench.harbor.model_map`` is NOT importable there
and the driver's *inline fallback* ``build_litellm_model`` is what actually runs in
production. These tests force that import to fail (``sys.modules[...] = None``) and
assert the fallback routes identically to the shared mapping -- in particular that
an OpenAI-compatible Gemini base (``/v1beta/openai``) routes through the openai
provider with the api_base preserved, the exact bug the M5 fix addressed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from clawbench.harbor import model_map as mm

_DRIVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "src/clawbench/runtime/harnesses/harbor/harbor_driver.py"
)


def _load_driver():
    """Load harbor_driver.py by path (it is a script, not an importable package)."""
    spec = importlib.util.spec_from_file_location(
        "harbor_driver_under_test", _DRIVER_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_DRIVER = _load_driver()


def _force_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``from clawbench.harbor.model_map import ...`` raise ImportError."""
    monkeypatch.setitem(sys.modules, "clawbench.harbor.model_map", None)


def test_fallback_gemini_openai_compat_routes_through_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # HIGH: the deployed inline fallback must NOT drop the /v1beta/openai api_base.
    _force_fallback(monkeypatch)
    model, api_base, env = _DRIVER.build_litellm_model(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-3.5-flash",
        "google-generative-ai",
        "k",
    )
    assert model == "openai/gemini-3.5-flash"
    assert api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert env == {"OPENAI_API_KEY": "k"}


def test_fallback_gemini_native_root_uses_gemini_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _force_fallback(monkeypatch)
    model, api_base, env = _DRIVER.build_litellm_model(
        "https://generativelanguage.googleapis.com",
        "gemini-3.5-flash",
        "google-generative-ai",
        "k",
    )
    assert model == "gemini/gemini-3.5-flash"
    assert api_base is None
    assert env == {"GEMINI_API_KEY": "k", "GOOGLE_API_KEY": "k"}


@pytest.mark.parametrize(
    "base_url,model,api_type",
    [
        (
            "https://generativelanguage.googleapis.com/v1beta/openai",
            "gemini-3.5-flash",
            "google-generative-ai",
        ),
        (
            "https://proxy.example.com/openai",
            "gemini-3.5-flash",
            "google-generative-ai",
        ),
        (
            "https://generativelanguage.googleapis.com",
            "gemini-3.5-flash",
            "google-generative-ai",
        ),
        ("https://api.anthropic.com", "claude-sonnet-4-6", "anthropic-messages"),
        ("https://proxy.example.com", "claude-sonnet-4-6", "anthropic-messages"),
        ("https://api.openai.com/v1/", "gpt-5", "openai-completions"),
        ("https://api.z.ai/api/paas/v4", "glm-5.1", "openai-completions"),
    ],
)
def test_fallback_matches_shared_model_map(
    monkeypatch: pytest.MonkeyPatch, base_url: str, model: str, api_type: str
) -> None:
    # The fallback must stay byte-for-byte equivalent to the shared mapping
    # (openrouter excluded: it hits the network to resolve the canonical id).
    _force_fallback(monkeypatch)
    fb_model, fb_base, fb_env = _DRIVER.build_litellm_model(
        base_url, model, api_type, "k"
    )
    shared = mm.build_litellm_model(base_url, model, api_type, "k")
    assert (fb_model, fb_base, fb_env) == (shared.model, shared.api_base, shared.env)


def test_uses_shared_mapping_when_importable() -> None:
    # When clawbench.harbor.model_map IS importable (the dev/editable env), the
    # driver delegates to it and gets the same correct routing.
    model, api_base, env = _DRIVER.build_litellm_model(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-3.5-flash",
        "google-generative-ai",
        "k",
    )
    assert model == "openai/gemini-3.5-flash"
    assert api_base == "https://generativelanguage.googleapis.com/v1beta/openai"
