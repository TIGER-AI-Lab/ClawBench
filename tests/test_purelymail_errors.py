from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from clawbench.runner.run_support import email as native_email

REPO_ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def load_harbor_script(name: str):
    path = REPO_ROOT / "src" / "clawbench" / "runtime" / "harbor" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "module",
    [
        native_email,
        pytest.param(load_harbor_script("prepare-task.py"), id="harbor-prepare"),
        pytest.param(load_harbor_script("cleanup-email.py"), id="harbor-cleanup"),
    ],
)
def test_purelymail_api_errors_fail_closed(monkeypatch, module) -> None:
    monkeypatch.setattr(
        module,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {
                "type": "error",
                "code": "invalidToken",
                "message": "Token not valid.",
            }
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=r"PurelyMail createUser failed \(invalidToken\): Token not valid\.",
    ):
        module.purelymail_request("createUser", {}, "secret-token")


def test_purelymail_rejects_non_object_responses(monkeypatch) -> None:
    monkeypatch.setattr(
        native_email,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(["unexpected"]),
    )

    with pytest.raises(RuntimeError, match="returned an invalid response"):
        native_email.purelymail_request("createUser", {}, "secret-token")
