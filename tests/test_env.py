"""AC-5: os.environ/ resolution."""
from __future__ import annotations

from conftest import summarize

CONFIG = """
model_list:
  - model_name: gpt-main
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/OPENAI_API_KEYY
      api_base: os.environ/FROM_SECOND_FILE
      organization: os.environ/FROM_CONFIG_ENV
      api_version: os.environ/FROM_PROCESS
"""


def write_envs(tmp_path):
    first = tmp_path / "a.env"
    first.write_text("# comment\nOPENAI_API_KEY=x\nexport OTHER=1\n", encoding="utf-8")
    second = tmp_path / "b.env"
    second.write_text("FROM_SECOND_FILE='value with = and spaces'\n", encoding="utf-8")
    return first, second


def test_env_sources_suggestion_and_kms(run, tmp_path, monkeypatch):
    first, second = write_envs(tmp_path)
    monkeypatch.setenv("FROM_PROCESS", "1")
    text = CONFIG + "environment_variables:\n  FROM_CONFIG_ENV: set-here\n"

    report = run(text, env_files=[first, second], use_os_env=True)
    errs = [d for d in report.diagnostics if d.code == "LL201"]
    assert len(errs) == 1  # only the typo'd name; the others resolve from other sources
    d = errs[0]
    assert d.severity.value == "error" and d.suggestion == "OPENAI_API_KEY"
    for source in (str(first), str(second), "process environment", "config environment_variables"):
        assert source in d.message

    # --no-os-env: the process environment is not searched, so FROM_PROCESS is missing too
    report = run(text, env_files=[first, second], use_os_env=False)
    errs = [d for d in report.diagnostics if d.code == "LL201"]
    assert len(errs) == 2
    assert all("process environment" not in d.message for d in errs)

    # key_management_system: the variable may live in the secret manager -> info
    report = run(
        text + "general_settings:\n  key_management_system: google_kms\n",
        env_files=[first, second],
        use_os_env=False,
    )
    levels = {d.severity.value for d in report.diagnostics if d.code == "LL201"}
    assert levels == {"info"}


def test_malformed_reference_does_not_echo_text(run):
    report = run(
        "model_list:\n  - model_name: a\n    litellm_params: {model: openai/x, api_key: 'os.environ/has space'}\n"
    )
    d = next(d for d in report.diagnostics if d.code == "LL201")
    assert "has space" not in d.message and "malformed" in d.message
    assert summarize(report).count(("LL201", "error", "model_list[0].litellm_params.api_key")) == 1
