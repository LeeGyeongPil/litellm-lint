"""AC-2: exit codes, output shape."""
from __future__ import annotations

import json

from litellm_lint.cli import main

from conftest import EXAMPLES, make_sentinel

ENV = str(EXAMPLES / ".env.example")


def test_exit_codes(tmp_path, capsys):
    assert main(["check", str(EXAMPLES / "good_config.yaml"), "--env-file", ENV, "--no-os-env"]) == 0
    out = capsys.readouterr().out
    assert out.strip().splitlines()[-1] == "0 errors, 0 warnings"

    assert main(["check", str(EXAMPLES / "bad_config.yaml"), "--env-file", ENV, "--no-os-env"]) == 1
    capsys.readouterr()

    secret = make_sentinel("yaml")
    broken = tmp_path / "broken.yaml"
    broken.write_text(f"general_settings:\n  master_key: [{secret}\n  other: 1\n", encoding="utf-8")
    assert main(["check", str(broken)]) == 2
    out = capsys.readouterr().out
    assert "LL900" in out and "cannot parse YAML" in out
    assert secret not in out
    assert str(broken) + ":" in out  # path:line:col of the problem


def test_usage_errors_exit_2(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing.yaml")]) == 2
    assert "not found" in capsys.readouterr().err
    good = str(EXAMPLES / "good_config.yaml")
    assert main(["check", good, "--env-file", str(tmp_path / "nope.env")]) == 2
    assert main(["check", good, "--ignore", "LL999"]) == 2
    assert "known codes" in capsys.readouterr().err
    assert main([]) == 2


def test_duplicate_key_is_a_parse_error_without_values(tmp_path, capsys):
    secret = make_sentinel("dup")
    path = tmp_path / "dup.yaml"
    path.write_text(f"general_settings:\n  master_key: {secret}\n  master_key: {secret}x\n", encoding="utf-8")
    assert main(["check", str(path)]) == 2
    out = capsys.readouterr().out
    assert "duplicate key" in out and secret not in out


def test_json_format_has_stable_fields(capsys):
    code = main(["check", str(EXAMPLES / "bad_config.yaml"), "--env-file", ENV, "--no-os-env", "--format", "json"])
    assert code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["snapshot"]["litellm_version"] == "1.108.4"
    assert data["summary"] == {"errors": 5, "warnings": 2, "info": 0}
    first = data["diagnostics"][0]
    assert set(first) == {"code", "severity", "message", "file", "line", "column", "key", "suggestion"}


def test_strict_and_ignore(tmp_path, capsys):
    path = tmp_path / "w.yaml"
    path.write_text("general_settings:\n  zzzz_future_setting: 1\n", encoding="utf-8")
    assert main(["check", str(path), "--no-os-env"]) == 0
    assert main(["check", str(path), "--no-os-env", "--strict"]) == 1
    assert main(["check", str(path), "--no-os-env", "--strict", "--ignore", "LL001"]) == 0
