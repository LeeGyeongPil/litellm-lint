"""AC-4: reference integrity without false positives."""
from __future__ import annotations

from conftest import summarize

MODELS = """
model_list:
  - model_name: gpt-main
    litellm_params: {model: openai/gpt-4o-mini, api_base: "http://127.0.0.1:9/v1", rpm: 10}
  - model_name: gpt-main
    litellm_params: {model: openai/gpt-4o-mini, api_base: "http://127.0.0.1:8/v1", rpm: 20}
  - model_name: "openai/*"
    litellm_params: {model: "openai/*"}
  - model_name: local-small
    litellm_params: {model: "ollama/qwen2.5:0.5b"}
"""


def refs(report):
    return [t for t in summarize(report) if t[0].startswith("LL1")]


def test_reference_resolution_without_false_positives(run):
    report = run(
        MODELS
        + """router_settings:
  model_group_alias:
    gpt-4: gpt-main
    gpt-4o: {model: gpt-main, hidden: true}
  fallbacks:
    - "*": [local-small]
    - gpt-4: [local-small]
  default_fallbacks: [local-small]
  model_group_retry_policy:
    gpt-main: {RateLimitErrorRetries: 3}
litellm_settings:
  fallbacks:
    - gpt-main: ["openai/gpt-4o", gpt-4o, local-small]
  content_policy_fallbacks:
    - openai/gpt-5: [local-small]
"""
    )
    # same model_name twice (load balancing), wildcard name, "*" source, both alias forms,
    # alias used as a fallback name: none of it is reported
    assert refs(report) == []
    assert report.diagnostics == []


def test_missing_targets_are_reported(run):
    report = run(
        MODELS
        + """router_settings:
  model_group_alias:
    gpt-4: gpt-mian
    gpt-4o: {model: nope, hidden: true}
  fallbacks:
    - ghost: [local-small]
    - gpt-main: [gpt-backup]
  model_group_retry_policy:
    ghost-group: {RateLimitErrorRetries: 1}
"""
    )
    got = refs(report)
    assert ("LL101", "error", "router_settings.fallbacks") in got
    assert ("LL102", "warning", "router_settings.fallbacks") in got
    assert got.count(("LL103", "error", "router_settings.model_group_alias")) == 2
    assert ("LL104", "warning", "router_settings.model_group_retry_policy") in got
    typo = next(d for d in report.diagnostics if d.code == "LL103" and "gpt-mian" in d.message)
    assert typo.suggestion == "gpt-main"


def test_store_model_in_db_downgrades_missing_targets(run):
    report = run(
        MODELS
        + """router_settings:
  fallbacks:
    - gpt-main: [gpt-backup]
  model_group_alias: {x: nope}
general_settings:
  store_model_in_db: true
"""
    )
    assert ("LL101", "warning", "router_settings.fallbacks") in summarize(report)
    assert ("LL103", "warning", "router_settings.model_group_alias") in summarize(report)
    assert report.errors == 0
