"""QA round 1 regressions: include files, alias bombs, deep nesting, many files, fallback shapes."""
from __future__ import annotations

import json
import time

from conftest import EXAMPLES, make_sentinel, summarize
from litellm_lint.cli import main

ENV = str(EXAMPLES / ".env.example")
MAIN = """include: [models.yaml]
model_list:
  - model_name: main
    litellm_params: {model: "ollama/qwen2.5:0.5b"}
router_settings:
  fallbacks:
    - main: [included-model]
"""
MODELS = """model_list:
  - model_name: included-model
    litellm_params: {model: "ollama/qwen2.5:0.5b"}
"""


def codes(report) -> list[str]:
    return [d.code for d in report.diagnostics]


# ---------------------------------------------------------------- include (Q-1)
def test_include_models_are_valid_fallback_targets(tmp_path, run):
    (tmp_path / "models.yaml").write_text(MODELS, encoding="utf-8")
    report = run(MAIN)
    assert report.diagnostics == []  # no LL001 for 'include', no LL101 for the included model


def test_include_is_resolved_next_to_the_declaring_file_and_nests(tmp_path, run):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "models.yaml").write_text("include: [sub/deeper.yaml]\n", encoding="utf-8")
    (sub / "deeper.yaml").write_text(MODELS, encoding="utf-8")
    assert run(MAIN).diagnostics == []


def test_include_cycle_is_tolerated(tmp_path, run):
    (tmp_path / "models.yaml").write_text(MODELS + "include: [config.yaml]\n", encoding="utf-8")
    assert run(MAIN).diagnostics == []  # the proxy reads each file once; so do we


def test_include_problems_are_clean_ll900(tmp_path, run):
    missing = run(MAIN)  # models.yaml does not exist
    assert codes(missing) == ["LL900"] and "include" in missing.diagnostics[0].message
    secret = make_sentinel("inc")
    (tmp_path / "models.yaml").write_text(f"- {secret}\n", encoding="utf-8")
    rep = run(MAIN)
    assert codes(rep) == ["LL900"] and secret not in rep.diagnostics[0].message
    (tmp_path / "models.yaml").write_text(f"model_list: [\n  {secret}\n", encoding="utf-8")
    rep = run(MAIN)
    assert codes(rep) == ["LL900"] and secret not in rep.diagnostics[0].message
    for bad in ("include: models.yaml\n", "include: [1, 2]\n"):
        rep = run(bad + "model_list: []\n")
        assert codes(rep) == ["LL002"], bad


def test_include_chain_has_a_limit(tmp_path, run):
    for i in range(80):
        (tmp_path / f"f{i}.yaml").write_text(f"include: [f{i + 1}.yaml]\n", encoding="utf-8")
    rep = run("include: [f0.yaml]\nmodel_list: []\n")
    assert codes(rep) == ["LL900"] and "too many" in rep.diagnostics[0].message


# ------------------------------------------------------ alias bomb / depth (Q-2, Q-3)
def _bomb(target: str) -> str:
    lines = ['a0: &a0 ["lol","lol","lol","lol","lol","lol","lol","lol","lol","lol"]']
    for i in range(1, 10):
        lines.append(f"a{i}: &a{i} [" + ",".join([f"*a{i - 1}"] * 10) + "]")
    return "\n".join(lines) + "\n" + target + "\n"


def test_alias_bomb_finishes_fast_with_ll900(run):
    for target in ("model_list: *a9", "environment_variables: {BOMB: *a9}"):
        start = time.monotonic()
        rep = run(_bomb(target))
        assert time.monotonic() - start < 2.0
        assert codes(rep) == ["LL900"] and "alias" in rep.diagnostics[0].message


def test_harmless_aliases_and_self_reference_still_work(run):
    rep = run(
        "defaults: &d {rpm: 10}\n"
        "model_list:\n"
        "  - model_name: a\n    litellm_params: {model: ollama/x, rpm: 10}\n"
        "router_settings: &r {num_retries: 2, self: *r}\n"
    )
    assert "LL900" not in codes(rep)


def test_deep_nesting_is_ll900_not_a_traceback(tmp_path, run):
    for text in ("router_settings: " + "[" * 5000 + "]" * 5000 + "\n", "router_settings:\n" + "".join(f"{' ' * i}a:\n" for i in range(1, 400))):
        rep = run(text)
        assert codes(rep) == ["LL900"] and "nesting" in rep.diagnostics[0].message


def test_cli_exit_2_for_bomb_and_depth(tmp_path, capsys):
    bomb = tmp_path / "bomb.yaml"
    bomb.write_text(_bomb("model_list: *a9"), encoding="utf-8")
    deep = tmp_path / "deep.yaml"
    deep.write_text("router_settings: " + "[" * 5000 + "]" * 5000 + "\n", encoding="utf-8")
    for path in (bomb, deep):
        assert main(["check", str(path), "--no-os-env"]) == 2
        out = capsys.readouterr()
        assert "Traceback" not in out.out + out.err


def test_unexpected_exception_becomes_internal_error(monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("secret-looking-value")

    monkeypatch.setattr("litellm_lint.cli.check_file", boom)
    assert main(["check", str(EXAMPLES / "good_config.yaml")]) == 2
    err = capsys.readouterr().err
    assert "internal error" in err and "RuntimeError" in err and "secret-looking-value" not in err


# --------------------------------------------------------------- many files (Q-4)
def test_check_accepts_several_files(capsys):
    good, bad = str(EXAMPLES / "good_config.yaml"), str(EXAMPLES / "bad_config.yaml")
    args = ["--env-file", ENV, "--no-os-env"]
    assert main(["check", good, *args, bad]) == 1  # max of the per-file codes
    out = capsys.readouterr().out
    assert good in out and bad in out
    assert main(["check", good, good, *args]) == 0
    capsys.readouterr()
    assert main(["check", *args, "--format", "json", good, bad]) == 1
    data = json.loads(capsys.readouterr().out)
    assert [d["file"] for d in data] == [good, bad]
    assert data[1]["summary"]["errors"] == 5


def test_exit_code_is_max_across_files(tmp_path, capsys):
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [\n", encoding="utf-8")
    assert main(["check", str(EXAMPLES / "bad_config.yaml"), str(broken), "--no-os-env"]) == 2
    capsys.readouterr()
    assert main(["check", str(EXAMPLES / "good_config.yaml"), str(tmp_path / "nope.yaml")]) == 2


def test_hook_passes_files_in_one_call():
    text = (EXAMPLES.parent / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "pass_filenames: true" in text and "require_serial" not in text


# --------------------------------------------------------- fallback shape (Q-6)
def test_fallback_element_shapes(run):
    rep = run(
        "model_list:\n  - model_name: a\n    litellm_params: {model: ollama/x}\n"
        "router_settings:\n  fallbacks: [{a: 5}, 7, {b: [null, 3, [x]]}, {a: [a], c: [a]}]\n"
        "  default_fallbacks: [a, 4, {x: y}]\n"
    )
    bad = [d for d in rep.diagnostics if d.code == "LL002" and d.key.startswith("router_settings.")]
    assert len(bad) >= 6
    assert all(d.line for d in bad)


def test_valid_fallback_shapes_stay_quiet(run):
    rep = run(
        "model_list:\n  - model_name: a\n    litellm_params: {model: ollama/x}\n"
        "  - model_name: b\n    litellm_params: {model: ollama/x}\n"
        "router_settings:\n  fallbacks:\n    - a: [b]\n    - b: [{model: a}]\n  default_fallbacks: [a, {model: b}]\n"
    )
    assert rep.diagnostics == []


def test_non_string_top_level_keys_are_reported(run):
    rep = run("1: 2\nmodel_list: []\n")
    assert ("LL002", "error", "1") in summarize(rep)
