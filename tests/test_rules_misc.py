"""AC-10: misplaced keys, duplicates, provider prefixes."""
from __future__ import annotations


def test_misplaced_duplicate_provider(run):
    report = run(
        """
model_list:
  - model_name: a
    litellm_params: {model: openai/gpt-4o-mini, api_base: "http://127.0.0.1:1"}
  - model_name: a
    litellm_params: {model: openai/gpt-4o-mini, api_base: "http://127.0.0.1:1"}
  - model_name: a
    litellm_params: {model: openai/gpt-4o-mini, api_base: "http://127.0.0.1:2"}
  - model_name: b
    litellm_params: {model: openai/gpt-4o-mini, api_base: "http://127.0.0.1:1"}
  - model_name: c
    litellm_params: {model: azrue/gpt-4o}
router_settings:
  health_check_interval: 30
"""
    )
    by_code = {}
    for d in report.diagnostics:
        by_code.setdefault(d.code, []).append(d)

    ll3 = by_code["LL003"][0]
    assert ll3.severity.value == "error" and "general_settings" in ll3.message
    assert "LL001" not in by_code  # not also reported as an unknown key

    # only the exact repeat (same name and params) is reported; same name with other
    # params (load balancing) and other name with the same params (alias) are not
    assert [d.key for d in by_code["LL401"]] == ["model_list[1]"]
    assert by_code["LL401"][0].severity.value == "warning"

    ll4 = by_code["LL402"][0]
    assert ll4.severity.value == "warning" and ll4.suggestion == "azure"
    assert "did you mean 'azure'" in ll4.message
    assert len(by_code["LL402"]) == 1  # openai/ is a known provider


def test_unknown_provider_without_suggestion_is_info(run):
    report = run("model_list:\n  - model_name: a\n    litellm_params: {model: mycorp-internal/model}\n")
    d = next(d for d in report.diagnostics if d.code == "LL402")
    assert d.severity.value == "info"
