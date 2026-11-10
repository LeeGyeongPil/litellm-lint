"""AC-6: secret values never reach any output."""
from __future__ import annotations

import json

from litellm_lint import report as report_mod
from litellm_lint.cli import main

from conftest import make_sentinel

API = make_sentinel("api")
MASTER = make_sentinel("master")
DOTENV = make_sentinel("dotenv")
ENVVAR = make_sentinel("envvar")
PASSWORD = make_sentinel("pw")


def test_secret_values_never_printed(run, tmp_path, capsys):
    envfile = tmp_path / "x.env"
    envfile.write_text(f"PRESENT={DOTENV}\nOPENAI_API_KEY={DOTENV}\n", encoding="utf-8")
    text = f"""
model_list:
  - model_name: gpt-main
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: {API}
      aws_secret_access_key: {PASSWORD}
  - model_name: other
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEYY
general_settings:
  master_key: sk-1234
  database_url: postgresql://u:{PASSWORD}@127.0.0.1/db
  alerting_password: {MASTER}
environment_variables:
  SOME_SERVICE_TOKEN: {ENVVAR}
"""
    report = run(text, env_files=[envfile])
    codes = {d.code for d in report.diagnostics}
    assert {"LL202", "LL301", "LL201"} <= codes
    assert report.errors >= 2

    rendered = [report_mod.format_text(report), report_mod.format_json(report)]
    config = tmp_path / "config.yaml"
    for fmt in ("text", "json"):
        assert main(["check", str(config), "--env-file", str(envfile), "--no-os-env", "--format", fmt]) == 1
        rendered.append(capsys.readouterr().out)
    blob = "\n".join(rendered)
    for secret in (API, MASTER, DOTENV, ENVVAR, PASSWORD, "sk-1234"):
        assert secret not in blob, "a secret value leaked into the output"
    json.loads(rendered[1])  # still valid JSON

    lines = {(d.code, d.key) for d in report.diagnostics}
    assert ("LL301", "general_settings.master_key") in lines
    assert ("LL202", "model_list[0].litellm_params.api_key") in lines
    assert ("LL202", "environment_variables.SOME_SERVICE_TOKEN") in lines


def test_weak_master_key_override_is_a_warning(run):
    report = run("general_settings:\n  master_key: sk-1234\n  dangerously_permit_weak_or_unset_master_key: true\n")
    d = next(d for d in report.diagnostics if d.code == "LL301")
    assert d.severity.value == "warning"


def test_empty_master_key_is_refused(run):
    report = run('general_settings:\n  master_key: ""\n')
    assert any(d.code == "LL301" and "empty" in d.message for d in report.diagnostics)
