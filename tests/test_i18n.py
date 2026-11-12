"""Output language: message tables, language decision order, Korean output, unchanged JSON."""
from __future__ import annotations

import json
import re
import string
from pathlib import Path

import pytest

import _lang  # noqa: F401  (pins LITELLM_LINT_LANG=en on import)
from litellm_lint import check_file, i18n
from litellm_lint.cli import main
from litellm_lint.report import format_text, format_text_many, summary

from conftest import EXAMPLES, ROOT

ENV = str(EXAMPLES / ".env.example")
BAD = str(EXAMPLES / "bad_config.yaml")
GOOD = str(EXAMPLES / "good_config.yaml")
HANGUL = re.compile(r"[가-힣]")


def _fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def _clear_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LITELLM_LINT_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(name, raising=False)


# ---- the message tables ---------------------------------------------------------


def test_en_and_ko_have_the_same_keys():
    assert set(i18n.EN) == set(i18n.KO)


def test_placeholders_match_between_languages():
    for key, template in i18n.EN.items():
        assert _fields(template) == _fields(i18n.KO[key]), key


def test_every_key_used_in_source_exists():
    used: set[str] = set()
    call = re.compile(r"""\b(?:msg|t)\(\s*(?:lang,\s*)?["']([a-z0-9_]+)["']""")
    for path in (ROOT / "src" / "litellm_lint").rglob("*.py"):
        if path.name != "i18n.py":
            used |= set(call.findall(path.read_text(encoding="utf-8")))
    assert used, "the pattern found no message keys"
    assert used <= set(i18n.EN), sorted(used - set(i18n.EN))


def test_every_key_is_used_somewhere():
    source = "".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "src" / "litellm_lint").rglob("*.py") if p.name != "i18n.py"
    )
    dynamic = ("n_", "sev_", "type_", "sep_")  # built from a variable: n_{noun}_.., sev_{value}, type_{word}
    for key in i18n.EN:
        if key.startswith(dynamic):
            continue
        assert f'"{key}"' in source, f"unused message key: {key}"


def test_korean_texts_use_one_politeness_level():
    # polite "-해요/-에요/-예요/-세요" endings are not used; the formal -ㅂ니다 style is
    for key, text in i18n.KO.items():
        assert not re.search(r"(해요|에요|예요|세요|네요|어요|아요)(?![가-힣])", text), key
    for text in i18n.ARGPARSE_KO.values():
        assert not re.search(r"(해요|에요|예요|세요)(?![가-힣])", text)


def test_korean_diagnostics_are_translated():
    # every message key whose English text is a full sentence has Hangul in Korean
    for key, text in i18n.KO.items():
        if key in {"sep_comma", "ll002_fb_where"}:
            continue
        assert HANGUL.search(text), key


# ---- language decision order -----------------------------------------------------


def test_resolve_language_priority(monkeypatch):
    _clear_locale(monkeypatch)
    assert i18n.resolve_language(None) == "en"
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    assert i18n.resolve_language(None) == "ko"
    assert i18n.resolve_language("en") == "en"  # flag beats everything
    monkeypatch.setenv("LITELLM_LINT_LANG", "en")
    assert i18n.resolve_language(None) == "en"  # tool variable beats LANG
    assert i18n.resolve_language("ko") == "ko"
    monkeypatch.setenv("LITELLM_LINT_LANG", "ko")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.resolve_language(None) == "ko"


def test_locale_variable_order_is_lc_all_then_lc_messages_then_lang(monkeypatch):
    _clear_locale(monkeypatch)
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    monkeypatch.setenv("LC_MESSAGES", "en_US.UTF-8")
    assert i18n.resolve_language(None) == "en"
    monkeypatch.setenv("LC_ALL", "ko_KR.UTF-8")
    assert i18n.resolve_language(None) == "ko"


@pytest.mark.parametrize("value", ["fr_FR.UTF-8", "C", "POSIX", "kok", "", "korean"])
def test_non_korean_or_invalid_values_mean_english(monkeypatch, value):
    _clear_locale(monkeypatch)
    monkeypatch.setenv("LANG", value)
    assert i18n.resolve_language(None) == "en"
    monkeypatch.delenv("LANG")
    monkeypatch.setenv("LITELLM_LINT_LANG", value)
    assert i18n.resolve_language(None) == "en"


def test_invalid_flag_value_falls_through_to_the_next_level(monkeypatch):
    _clear_locale(monkeypatch)
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    assert i18n.resolve_language("fr") == "ko"


def test_prescan_finds_the_flag_anywhere():
    assert i18n.prescan_lang_flag(["check", "x.yaml", "--lang", "ko"]) == "ko"
    assert i18n.prescan_lang_flag(["--lang=ko", "check"]) == "ko"
    assert i18n.prescan_lang_flag(["--lang", "ko", "check", "--lang", "en"]) == "en"
    assert i18n.prescan_lang_flag(["check", "--lang"]) is None
    assert i18n.prescan_lang_flag(["check"]) is None


# ---- CLI behaviour ---------------------------------------------------------------


def _run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_help_follows_lang_environment(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    out = capsys.readouterr().out
    assert "사용법:" in out and "위치 인자:" in out and "옵션:" in out and "--lang" in out
    assert "usage:" not in out and "positional arguments" not in out


def test_environment_tool_variable_beats_locale(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    monkeypatch.setenv("LITELLM_LINT_LANG", "en")
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "usage:" in out and not HANGUL.search(out)


@pytest.mark.parametrize("where", ["top", "after-command"])
def test_lang_flag_works_at_every_position(monkeypatch, capsys, where):
    _clear_locale(monkeypatch)
    args = ["--lang", "ko", "check", BAD] if where == "top" else ["check", BAD, "--lang", "ko"]
    code, out, _ = _run(capsys, *args, "--env-file", ENV, "--no-os-env")
    assert code == 1
    assert "오류 LL" in out and out.strip().splitlines()[-1].startswith("오류 ")


def test_lang_en_beats_korean_locale(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")
    code, out, _ = _run(capsys, "--lang", "en", "check", BAD, "--env-file", ENV, "--no-os-env")
    assert code == 1
    assert not HANGUL.search(out)
    assert out.strip().splitlines()[-1] == "5 errors, 2 warnings"


def test_korean_text_report_shape(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    code, out, _ = _run(capsys, "--lang", "ko", "check", BAD, "--env-file", ENV, "--no-os-env")
    assert code == 1
    lines = out.strip().splitlines()
    assert lines[0].startswith("litellm-lint 0.2.0 (스키마 스냅숏: litellm ")
    assert lines[-1] == "오류 5건, 경고 2건"
    assert any(" 오류 LL101 " in line and "model_name" in line for line in lines)
    assert any(" 경고 LL001 " in line for line in lines)
    assert all(re.search(r"\b(error|warning)\b", line) is None for line in lines[1:-1])


def test_korean_check_help_and_choices_error(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    with pytest.raises(SystemExit):
        main(["check", "--help", "--lang", "ko"])
    out = capsys.readouterr().out
    assert "--env-file" in out and "--strict" in out
    assert "경고만 있어도" in out and "skip" not in out and "comma-separated" not in out

    with pytest.raises(SystemExit) as stop:
        main(["check", BAD, "--format", "xml", "--lang", "ko"])
    assert stop.value.code == 2
    err = capsys.readouterr().err
    assert "오류" in err and "--format" in err
    assert re.search(r"잘못된 선택입니다: .?xml.? ", err)
    assert "invalid choice" not in err

    with pytest.raises(SystemExit):
        main(["check", BAD, "--format", "xml", "--lang", "en"])
    assert re.search(r"invalid choice: .?xml.? ", capsys.readouterr().err)


def test_korean_argparse_missing_argument_and_unknown_option(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    with pytest.raises(SystemExit):
        main(["check", "--lang", "ko"])
    err = capsys.readouterr().err
    assert "다음 인자가 필요합니다" in err and "config" in err
    with pytest.raises(SystemExit):
        main(["check", BAD, "--nope", "--lang", "ko"])
    assert "인식할 수 없는 인자입니다: --nope" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(["check", BAD, "--ignore", "--lang", "ko"])
    assert "인자가 하나 필요합니다" in capsys.readouterr().err


def test_korean_usage_errors_and_no_command(monkeypatch, capsys, tmp_path):
    _clear_locale(monkeypatch)
    code, _, err = _run(capsys, "--lang", "ko", "check", str(tmp_path / "missing.yaml"))
    assert code == 2
    assert err.startswith("litellm-lint: 오류: 설정 파일을 찾을 수 없습니다")
    code, _, err = _run(capsys, "--lang", "ko", "check", GOOD, "--env-file", str(tmp_path / "nope.env"))
    assert code == 2 and "env 파일을 찾을 수 없습니다" in err
    code, _, err = _run(capsys, "--lang", "ko", "check", GOOD, "--ignore", "LL999")
    assert code == 2 and "알 수 없는 규칙 코드 'LL999'" in err and "LL001" in err
    code, _, err = _run(capsys, "--lang", "ko")
    assert code == 2 and "명령을 고르십시오" in err and "사용법:" in err
    code, out, _ = _run(capsys, "--lang", "ko", "--version")
    assert code == 0 and out.startswith("litellm-lint 0.2.0 (스키마 스냅숏: litellm ")


def test_english_usage_errors_unchanged(monkeypatch, capsys, tmp_path):
    _clear_locale(monkeypatch)
    code, _, err = _run(capsys, "check", str(tmp_path / "missing.yaml"))
    assert code == 2 and err.startswith("litellm-lint: error: config file not found:")
    code, _, err = _run(capsys)
    assert code == 2 and "choose a command: check or schema" in err


def test_korean_yaml_problem_and_included_file_messages(monkeypatch, capsys, tmp_path):
    _clear_locale(monkeypatch)
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [1\nb: 2\n", encoding="utf-8")
    code, out, _ = _run(capsys, "--lang", "ko", "check", str(broken))
    assert code == 2 and " 오류 LL900 YAML 을 해석할 수 없습니다: " in out
    dup = tmp_path / "dup.yaml"
    dup.write_text("a: 1\na: 2\n", encoding="utf-8")
    code, out, _ = _run(capsys, "--lang", "ko", "check", str(dup))
    assert code == 2 and "중복된 키입니다" in out
    inc = tmp_path / "inc.yaml"
    inc.write_text("include: [nope.yaml]\n", encoding="utf-8")
    code, out, _ = _run(capsys, "--lang", "ko", "check", str(inc))
    assert code == 2 and "포함된 파일을 찾을 수 없습니다: nope.yaml" in out
    listy = tmp_path / "listy.yaml"
    listy.write_text("- 1\n", encoding="utf-8")
    code, out, _ = _run(capsys, "--lang", "ko", "check", str(listy))
    assert code == 2 and "최상위는 매핑" in out


def test_korean_summary_for_several_files(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    code, out, _ = _run(capsys, "--lang", "ko", "check", GOOD, BAD, "--env-file", ENV, "--no-os-env")
    assert code == 1
    lines = out.strip().splitlines()
    assert lines[-1] == "합계: 파일 2개, 오류 5건, 경고 2건"
    assert any(line.endswith("good_config.yaml: 오류 0건, 경고 0건") for line in lines)


def test_korean_plural_forms_have_no_plural_suffix():
    for n in (0, 1, 2, 5):
        assert i18n.plural("ko", "error", n) == f"오류 {n}건"
    assert i18n.plural("en", "error", 1) == "1 error"
    assert i18n.plural("en", "error", 0) == "0 errors"
    assert i18n.plural("en", "file", 1) == "1 file"


# ---- per-rule Korean rendering through the public report API -----------------------

RULE_CONFIG = """\
model_list:
  - model_name: gpt
    litellm_params:
      model: opnai/gpt-4o
      api_key: sk-literal
      api_bse: http://127.0.0.1:1
  - model_name: gpt
    litellm_params:
      model: opnai/gpt-4o
      api_key: sk-literal
      api_bse: http://127.0.0.1:1
  - 7
  - litellm_params: {}
router_settings:
  num_retries: [1]
  allowed_fails: 3
  num_retires: 3
  fallbacks:
    - gpt: [gptt]
    - 5
    - {1: x}
  default_fallbacks: [7]
  model_group_alias: {old: gptt}
  model_group_retry_policy: {gptz: {}}
general_settings:
  master_key: ""
  alerting: {}
litellm_settings:
  fallbacks: nope
  request_timeout: os.environ/NOT_SET_ANYWHERE_NAME
environment_variables: []
include: 3
"""


def test_every_diagnostic_renders_in_korean(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text(RULE_CONFIG, encoding="utf-8")
    report = check_file(path, use_os_env=False)
    codes = {d.code for d in report.diagnostics}
    assert {"LL001", "LL002", "LL101", "LL201", "LL202", "LL301", "LL401", "LL402"} <= codes
    text = format_text(report, "ko")
    for line in text.splitlines()[1:-1]:
        assert HANGUL.search(line.split(" LL", 1)[1]), line  # message part is Korean
    # the English rendering is exactly what Diagnostic.message holds
    english = format_text(report, "en")
    for d in report.diagnostics:
        assert d.message in english


def test_korean_rendering_of_kms_and_store_in_db_variants(tmp_path):
    path = tmp_path / "kms.yaml"
    path.write_text(
        "general_settings: {key_management_system: aws_secret_manager, store_model_in_db: true}\n"
        "model_list:\n  - model_name: a\n    litellm_params: {model: openai/x, api_key: os.environ/OPENAI_KEYY}\n"
        "router_settings: {fallbacks: [{a: [b]}], model_group_alias: {z: bb}}\n"
        "environment_variables: {OPENAI_KEY: x}\n",
        encoding="utf-8",
    )
    report = check_file(path, use_os_env=False)
    text = format_text(report, "ko")
    assert "비밀 관리자에서 읽을 수도 있습니다" in text
    assert "store_model_in_db 가 켜져 있어 경고로만 표시합니다" in text
    assert "설정의 environment_variables" in text
    assert "can be read" not in text and "warning only" not in text


def test_text_many_and_summary_accept_language(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_text("model_list: []\n", encoding="utf-8")
    report = check_file(path, use_os_env=False)
    assert summary(report) == "0 errors, 0 warnings"
    assert summary(report, "ko") == "오류 0건, 경고 0건"
    assert format_text_many([report, report], "ko").splitlines()[-1].startswith("합계: 파일 2개")


# ---- machine output is language independent ------------------------------------------


def test_json_output_is_byte_identical_in_both_languages(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    outputs = []
    for lang in ("en", "ko"):
        code, out, _ = _run(capsys, "--lang", lang, "check", BAD, "--env-file", ENV, "--no-os-env", "--format", "json")
        assert code == 1
        outputs.append(out)
    assert outputs[0] == outputs[1]
    assert not HANGUL.search(outputs[0])
    assert json.loads(outputs[0])["summary"] == {"errors": 5, "warnings": 2, "info": 0}


def test_json_for_several_files_and_broken_yaml_is_language_independent(monkeypatch, capsys, tmp_path):
    _clear_locale(monkeypatch)
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [1\n", encoding="utf-8")
    results = []
    for lang in ("en", "ko"):
        code, out, _ = _run(capsys, "--lang", lang, "check", GOOD, str(broken), BAD, "--no-os-env", "--format", "json")
        assert code == 2
        results.append(out)
    assert results[0] == results[1]


def test_schema_export_is_language_independent(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    _, en_out, _ = _run(capsys, "--lang", "en", "schema")
    _, ko_out, _ = _run(capsys, "--lang", "ko", "schema")
    assert en_out == ko_out
    assert json.loads(en_out)["$schema"]


def test_schema_output_file_message_is_localized(monkeypatch, capsys, tmp_path):
    _clear_locale(monkeypatch)
    target = tmp_path / "schema.json"
    _, out, _ = _run(capsys, "--lang", "ko", "schema", "-o", str(target))
    assert out.strip() == f"{target} 에 썼습니다"
    assert Path(target).read_text(encoding="utf-8")


def test_exit_codes_do_not_depend_on_language(monkeypatch, capsys):
    _clear_locale(monkeypatch)
    for argv in (["check", BAD], ["check", GOOD, "--env-file", ENV], ["check", GOOD, "--strict", "--no-os-env"]):
        codes = {_run(capsys, "--lang", lang, *argv, "--no-os-env")[0] for lang in ("en", "ko")}
        assert len(codes) == 1


def test_diagnostic_message_stays_english_and_str():
    path = EXAMPLES / "bad_config.yaml"
    report = check_file(path, env_files=[ENV], use_os_env=False)
    for d in report.diagnostics:
        assert isinstance(d.message, str)
        assert not HANGUL.search(d.message)
        assert not HANGUL.search(json.dumps(d.as_dict(), ensure_ascii=False))
