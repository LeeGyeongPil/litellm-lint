"""AC-3: severity policy for unknown keys, plus type checks."""
from __future__ import annotations

from conftest import summarize

BASE = """
model_list:
  - model_name: gpt-main
    litellm_params:
      model: openai/gpt-4o-mini
      api_key: os.environ/K
"""


def find(report, key):
    return next(d for d in report.diagnostics if d.key == key)


def test_unknown_key_severity_policy(run):
    report = run(
        BASE
        + """      api_bse: x
      totally_custom_provider_arg: 1
router_settings:
  num_retires: 3
  zzzz_future_setting: 1
  drop_params: true
general_settings:
  num_retries: 2
""",
        ignore=["LL201"],
    )
    # close key in the same section -> error + suggestion
    d = find(report, "router_settings.num_retires")
    assert (d.code, d.severity.value, d.suggestion) == ("LL001", "error", "num_retries")
    # nothing close -> warning that mentions the snapshot
    d = find(report, "router_settings.zzzz_future_setting")
    assert d.severity.value == "warning" and "snapshot" in d.message
    # key that exists in another section -> error + "belongs in"
    d = find(report, "router_settings.drop_params")
    assert d.severity.value == "error" and "belongs in litellm_settings" in d.message
    d = find(report, "general_settings.num_retries")
    assert d.severity.value == "error" and "belongs in router_settings" in d.message
    # litellm_params is extra="allow" in the proxy: suggestion -> warning, none -> info
    d = find(report, "model_list[0].litellm_params.api_bse")
    assert (d.severity.value, d.suggestion) == ("warning", "api_base")
    d = find(report, "model_list[0].litellm_params.totally_custom_provider_arg")
    assert d.severity.value == "info"


def test_strict_and_ignore_flags(run):
    text = BASE + "router_settings:\n  zzzz_future_setting: 1\n"
    report = run(text, ignore=["LL201"])
    assert (report.errors, report.warnings) == (0, 1)
    assert report.exit_code() == 0
    assert report.exit_code(strict=True) == 1
    report = run(text, ignore=["ll201", "LL001"])
    assert report.diagnostics == []


def test_type_checks(run):
    report = run(
        BASE
        + """router_settings:
  num_retries: three
  default_fallbacks: gpt-main
  timeout: os.environ/TIMEOUT
  allowed_fails: "3"
litellm_settings:
  fallbacks: gpt-main
  drop_params: whatever-goes
general_settings: [1, 2]
""",
        ignore=["LL201"],
    )
    got = {(d.code, d.key) for d in report.diagnostics}
    assert ("LL002", "router_settings.num_retries") in got
    assert ("LL002", "router_settings.default_fallbacks") in got
    assert ("LL002", "litellm_settings.fallbacks") in got
    assert ("LL002", "general_settings") in got
    # os.environ/ references, numeric text and setattr-style keys are not flagged
    assert ("LL002", "router_settings.timeout") not in got
    assert ("LL002", "router_settings.allowed_fails") not in got
    assert ("LL002", "litellm_settings.drop_params") not in got


def test_model_list_shape(run):
    report = run(
        "model_list:\n"
        "  - litellm_params: {model: openai/x}\n"
        "  - model_name: a\n"
        "  - model_name: b\n"
        "    litellm_params: {api_base: x}\n"
    )
    codes = summarize(report)
    assert ("LL002", "error", "model_list[0]") in codes  # no model_name
    assert ("LL002", "error", "model_list[1]") in codes  # no litellm_params
    assert ("LL002", "error", "model_list[2].litellm_params") in codes  # no model
