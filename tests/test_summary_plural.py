"""Summary lines use singular/plural correctly; JSON output and exit codes are unchanged."""
from __future__ import annotations

import json

import pytest

from litellm_lint.cli import main
from litellm_lint.diagnostics import Diagnostic, Report, Severity
from litellm_lint.report import summary

from conftest import EXAMPLES

ENV = str(EXAMPLES / ".env.example")

WARN_ONLY = """\
model_list:
  - model_name: gpt
    litellm_params:
      model: openai/gpt-4o
      api_key: sk-literal
"""
ERR_ONLY = """\
model_list:
  - model_name: gpt
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/LLTEST_UNSET_NAME
"""


def _report(errors: int, warnings: int, infos: int = 0) -> Report:
    diags = []
    for sev, n in ((Severity.ERROR, errors), (Severity.WARNING, warnings), (Severity.INFO, infos)):
        diags += [Diagnostic("LLX", sev, "m", "f.yaml") for _ in range(n)]
    return Report(path="f.yaml", diagnostics=diags)


@pytest.mark.parametrize(
    ("errors", "warnings", "expected"),
    [
        (0, 0, "0 errors, 0 warnings"),
        (0, 1, "0 errors, 1 warning"),
        (1, 0, "1 error, 0 warnings"),
        (1, 1, "1 error, 1 warning"),
        (1, 2, "1 error, 2 warnings"),
        (2, 1, "2 errors, 1 warning"),
        (5, 2, "5 errors, 2 warnings"),
    ],
)
def test_summary_combinations(errors, warnings, expected):
    assert summary(_report(errors, warnings)) == expected


def test_summary_info_tail_unchanged():
    assert summary(_report(1, 1, infos=3)) == "1 error, 1 warning, 3 info"


def _write(tmp_path):
    warn = tmp_path / "warn.yaml"
    err = tmp_path / "err.yaml"
    warn.write_text(WARN_ONLY)
    err.write_text(ERR_ONLY)
    return warn, err


def test_single_file_lines_and_exit_codes(tmp_path, capsys):
    warn, err = _write(tmp_path)
    assert main(["check", str(warn), "--no-os-env"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "0 errors, 1 warning"
    assert main(["check", str(warn), "--no-os-env", "--strict"]) == 1
    capsys.readouterr()
    assert main(["check", str(err), "--no-os-env"]) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == "1 error, 0 warnings"


def test_many_files_total_line(tmp_path, capsys):
    warn, err = _write(tmp_path)
    assert main(["check", str(warn), str(err), "--no-os-env"]) == 1
    lines = capsys.readouterr().out.strip().splitlines()
    assert f"{warn}: 0 errors, 1 warning" in lines
    assert f"{err}: 1 error, 0 warnings" in lines
    assert lines[-1] == "total: 2 files, 1 error, 1 warning"


def test_json_unchanged(tmp_path, capsys):
    warn, err = _write(tmp_path)
    assert main(["check", str(err), "--no-os-env", "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["summary"] == {"errors": 1, "warnings": 0, "info": 0}
    assert main(["check", str(warn), str(err), "--no-os-env", "--format", "json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert [d["summary"] for d in data] == [
        {"errors": 0, "warnings": 1, "info": 0},
        {"errors": 1, "warnings": 0, "info": 0},
    ]


def test_example_files_plural_unchanged(capsys):
    good, bad = str(EXAMPLES / "good_config.yaml"), str(EXAMPLES / "bad_config.yaml")
    assert main(["check", good, bad, "--env-file", ENV, "--no-os-env"]) == 1
    lines = capsys.readouterr().out.strip().splitlines()
    assert f"{good}: 0 errors, 0 warnings" in lines
    assert f"{bad}: 5 errors, 2 warnings" in lines
    assert lines[-1] == "total: 2 files, 5 errors, 2 warnings"
