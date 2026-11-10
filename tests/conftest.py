"""Shared fixtures.

Every test runs with the network blocked and ``import litellm`` blocked: litellm-lint must
work from its built-in snapshot alone. Set LITELLM_LINT_ALLOW_LITELLM=1 to lift both
blocks (only the optional snapshot-generation test needs that).
"""
from __future__ import annotations

import importlib.abc
import os
import socket
import sys
from pathlib import Path

import pytest

from litellm_lint import Report, check_file

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def make_sentinel(tag: str) -> str:
    """Watch string for the redaction tests, assembled at run time so that no
    secret-looking literal sits in the source or in the compiled .pyc files."""
    return "".join(["canary", "_", tag, "_", "7c1e", "9d"])


class _BlockLitellm(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
        if fullname == "litellm" or fullname.startswith("litellm."):
            raise ImportError("litellm is blocked in litellm-lint tests (set LITELLM_LINT_ALLOW_LITELLM=1)")
        return None


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch):
    if os.environ.get("LITELLM_LINT_ALLOW_LITELLM") == "1":
        yield
        return

    def no_connect(self, *args, **kwargs):  # noqa: ANN001
        raise AssertionError("network access attempted in a litellm-lint test")

    monkeypatch.setattr(socket.socket, "connect", no_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", no_connect)
    finder = _BlockLitellm()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)


@pytest.fixture
def run(tmp_path: Path):
    """run(yaml_text, **kw) -> Report. Defaults to no process environment."""

    def _run(text: str, name: str = "config.yaml", **kwargs) -> Report:
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        kwargs.setdefault("use_os_env", False)
        return check_file(path, **kwargs)

    return _run


def summarize(report: Report) -> list[tuple[str, str, str]]:
    """[(code, severity, key)] for compact assertions."""
    return [(d.code, d.severity.value, d.key) for d in report.diagnostics]
