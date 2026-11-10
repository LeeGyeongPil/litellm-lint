"""AC-1 and false-positive regression."""
from __future__ import annotations

from litellm_lint import check_file

from conftest import EXAMPLES

ENV = EXAMPLES / ".env.example"

PROBE_GOOD = """
model_list:
  - model_name: fake-gpt
    litellm_params:
      model: openai/fake
      api_key: os.environ/OPENAI_API_KEY
      api_base: http://127.0.0.1:9/
      mock_response: "hello from mock"
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
"""

# Shape of the config example in the LiteLLM docs (docs.litellm.ai/docs/proxy/configs),
# completed with the local-small model the docs snippet leaves out.
DOCS_STYLE = """
model_list:
  - model_name: gpt-main
    litellm_params:
      model: azure/gpt-4o
      api_base: os.environ/AZURE_API_BASE
      api_key: os.environ/AZURE_API_KEY
      rpm: 60
  - model_name: local-small
    litellm_params:
      model: ollama/qwen2.5
      api_base: http://127.0.0.1:11434
  - model_name: "openai/*"
    litellm_params:
      model: "openai/*"
      api_key: os.environ/OPENAI_API_KEY
router_settings:
  routing_strategy: simple-shuffle
  model_group_alias: {"gpt-4": "gpt-main"}
litellm_settings:
  drop_params: true
  fallbacks: [{"gpt-main": ["local-small"]}]
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
environment_variables:
  AZURE_API_BASE: http://127.0.0.1:1
  AZURE_API_KEY: os.environ/OPENAI_API_KEY
"""


def test_bad_config_reports_probe_errors():
    report = check_file(EXAMPLES / "bad_config.yaml", env_files=[ENV], use_os_env=False)
    got = {(d.code, d.severity.value, d.key, d.line, d.col) for d in report.diagnostics}
    expected = {
        ("LL201", "error", "model_list[0].litellm_params.api_key", 7, 16),
        ("LL001", "warning", "model_list[2].litellm_params.api_bse", 17, 7),
        ("LL001", "error", "router_settings.num_retires", 20, 3),
        ("LL101", "error", "router_settings.fallbacks", 22, 18),
        ("LL001", "error", "litellm_settings.drop_parms", 24, 3),
        ("LL101", "error", "litellm_settings.context_window_fallbacks", 26, 21),
        ("LL001", "warning", "general_settings.maser_key_typo", 29, 3),
    }
    assert got == expected
    by_key = {d.key: d for d in report.diagnostics}
    assert by_key["litellm_settings.drop_parms"].suggestion == "drop_params"
    assert by_key["router_settings.num_retires"].suggestion == "num_retries"
    assert by_key["model_list[2].litellm_params.api_bse"].suggestion == "api_base"
    assert by_key["model_list[0].litellm_params.api_key"].suggestion == "OPENAI_API_KEY"


def test_good_example_is_clean():
    report = check_file(EXAMPLES / "good_config.yaml", env_files=[ENV], use_os_env=False)
    assert report.diagnostics == []


def test_known_good_configs_have_no_errors(run):
    """False-positive guard: the probe's working config and a docs-style config."""
    for text in (PROBE_GOOD, DOCS_STYLE):
        report = run(text, env_files=[ENV])
        assert report.errors == 0, [d.message for d in report.diagnostics]
        assert report.warnings == 0, [d.message for d in report.diagnostics]
