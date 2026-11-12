"""AC-7: offline operation and version labelling."""
from __future__ import annotations

import json
import socket

import pytest

from litellm_lint import check_file, snapshot
from litellm_lint.cli import main

from conftest import EXAMPLES


def test_version_display_offline_and_mismatch(monkeypatch, capsys):
    # the fixture really blocks litellm and the network
    with pytest.raises(ImportError):
        import litellm  # noqa: F401
    with pytest.raises(AssertionError):
        socket.socket().connect(("127.0.0.1", 9))

    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "litellm-lint 0.2.0 (schema snapshot: litellm 1.108.4)"

    good = str(EXAMPLES / "good_config.yaml")
    env = str(EXAMPLES / ".env.example")
    main(["check", good, "--env-file", env, "--no-os-env"])
    assert capsys.readouterr().out.splitlines()[0].startswith("litellm-lint 0.2.0 (schema snapshot: litellm 1.108.4")
    main(["check", good, "--env-file", env, "--no-os-env", "--format", "json"])
    assert json.loads(capsys.readouterr().out)["snapshot"]["litellm_version"] == "1.108.4"

    # installed litellm with another version (fake metadata) -> LL000 info, exit stays 0
    monkeypatch.setattr(snapshot.importlib_metadata, "version", lambda name: "1.109.0")
    report = check_file(good, env_files=[env], use_os_env=False)
    ll0 = [d for d in report.diagnostics if d.code == "LL000"]
    assert len(ll0) == 1 and ll0[0].severity.value == "info"
    assert "1.109.0" in ll0[0].message and "1.108.4" in ll0[0].message
    assert report.exit_code() == 0

    # same version -> silent
    monkeypatch.setattr(snapshot.importlib_metadata, "version", lambda name: "1.108.4")
    assert check_file(good, env_files=[env], use_os_env=False).diagnostics == []
