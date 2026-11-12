"""Output language (English / Korean): one message table, one language decision.

Every sentence a person reads lives in ``EN`` and ``KO`` below, keyed by name. Rules build
messages with :func:`msg`; the result is an ordinary ``str`` holding the English text (so
JSON output, ``Diagnostic.message`` and library users never change) that also remembers its
key and arguments, so the text report can render it again in another language with
:func:`localize`.

The CLI picks the language with :func:`resolve_language`:
``--lang en|ko`` > ``LITELLM_LINT_LANG`` > ``LC_ALL`` / ``LC_MESSAGES`` / ``LANG``;
anything that is not Korean (or not valid) means English.
"""
from __future__ import annotations

import contextlib
import os
from typing import Any, Iterator, Mapping, Sequence

LANGUAGES = ("en", "ko")
DEFAULT_LANGUAGE = "en"
ENV_VAR = "LITELLM_LINT_LANG"

EN: dict[str, str] = {
    # --- CLI -------------------------------------------------------------
    "cli_description": "Static checks for LiteLLM proxy config.yaml (unofficial). Does not start the proxy or call any API.",
    "help_version": "show version and schema snapshot, then exit",
    "help_lang": "output language: en or ko (default: LITELLM_LINT_LANG, then LC_ALL/LC_MESSAGES/LANG, else en)",
    "help_check": "check a config file (exit 0 clean, 1 findings, 2 usage or YAML error)",
    "help_config": "path(s) to the proxy config.yaml (several files: exit code is the worst one)",
    "help_env_file": "dotenv file whose names count as defined (repeatable)",
    "help_no_os_env": "do not count the current process environment",
    "help_strict": "exit 1 on warnings too",
    "help_ignore": "comma-separated rule codes to skip, e.g. LL001,LL402",
    "help_format": "output format (default: text)",
    "help_schema": "export a JSON Schema for editors (yaml-language-server)",
    "help_output": "write to a file instead of stdout",
    "version_text": "litellm-lint {version} (schema snapshot: litellm {snapshot})",
    "cli_error": "litellm-lint: error: {text}",
    "cli_no_command": "choose a command: check or schema (see --help)",
    "cli_unrecognized": "unrecognized arguments: {args}",
    "cli_internal_error": (
        "litellm-lint: internal error ({name}); exit 2. Please report it with a minimal config "
        "that triggers it (remove secrets first)."
    ),
    "cli_wrote": "wrote {path}",
    # --- report ----------------------------------------------------------
    "report_header": "litellm-lint {version} (schema snapshot: litellm {snapshot}, generated {generated})",
    "n_error_one": "{n} error",
    "n_error_other": "{n} errors",
    "n_warning_one": "{n} warning",
    "n_warning_other": "{n} warnings",
    "n_info_one": "{n} info",
    "n_info_other": "{n} info",
    "n_file_one": "{n} file",
    "n_file_other": "{n} files",
    "total_line": "total: {files}, {errors}, {warnings}",
    "sev_error": "error",
    "sev_warning": "warning",
    "sev_info": "info",
    "sep_or": " or ",
    "sep_comma": ", ",
    # --- shared words ----------------------------------------------------
    "kind_mapping": "a mapping",
    "kind_list": "a list",
    "kind_boolean": "a boolean",
    "kind_number": "a number",
    "kind_text": "text",
    "kind_empty": "an empty value",
    "type_string": "string",
    "type_number": "number",
    "type_integer": "integer",
    "type_boolean": "boolean",
    "type_object": "object",
    "type_array": "array",
    "did_you_mean": " (did you mean '{hint}'?)",
    "why_db": " (warning only: store_model_in_db is on)",
    "why_empty": " (warning only: model_list is empty or absent)",
    # --- input problems (exit code 2) ------------------------------------
    "config_not_found": "config file not found: {path}. Check the path or run from the project directory.",
    "config_unreadable": "cannot read {path} as UTF-8 text ({name}).",
    "env_file_not_found": "env file not found: {path}. Fix the --env-file path or remove the option.",
    "env_file_unreadable": "cannot read env file {path} ({name}).",
    "unknown_rule_code": "unknown rule code {code!r} in --ignore; known codes: {known}",
    # --- LL900 -----------------------------------------------------------
    "yaml_cannot_parse": "cannot parse YAML: {what}",
    "yaml_duplicate_key": "duplicate key (the proxy would silently keep only the last one)",
    "yaml_invalid_construct": "the YAML construct is not valid",
    "yaml_too_deep": "nesting too deep: the document is nested more than {limit} levels",
    "yaml_too_big": "too many alias expansions: the document expands to more than {limit} nodes (possible YAML alias bomb)",
    "yaml_parser_gave_up": "nesting too deep: the parser gave up (limit {limit} levels)",
    "yaml_walk_too_deep": "nesting too deep: the document could not be walked",
    "root_not_mapping": "the config root must be a mapping (key: value pairs)",
    "inc_unresolvable": "included file cannot be resolved",
    "inc_too_many": "too many included files (limit {limit}); is the include chain endless?",
    "inc_not_found": (
        "included file not found: {entry} (the proxy would fail to start; paths are relative to the file that lists them)"
    ),
    "inc_unreadable": "included file cannot be read as UTF-8 text",
    "inc_not_mapping": "included file must be a mapping (key: value pairs)",
    "inc_bad_include": "'include' in an included file must be a list of file paths",
    # --- LL000 -----------------------------------------------------------
    "ll000": (
        "installed litellm {installed} differs from schema snapshot {snapshot}; "
        "keys added in newer releases may be reported as unknown"
    ),
    # --- LL001-LL003 -----------------------------------------------------
    "ll003_misplaced": (
        "'{key}' is not a valid router_settings key; move it to {target} (the proxy refuses to start with this error)"
    ),
    "ll001_wrong_section": "unknown key '{key}' in {section}; it belongs in {names}",
    "ll001_hint": "unknown key '{key}' in {section} (did you mean '{hint}'?)",
    "ll001_param_info": "key '{key}' in {section} is not a common parameter; the proxy passes it on to the provider",
    "ll001_snapshot": (
        "unknown key '{key}' in {section}: not in the litellm {version} snapshot (may be a newer setting, or a typo)"
    ),
    "ll002_type": "'{path}' should be {expected}, found {found}",
    "ll002_key_not_text": "a top-level key is not text (keys must be names like 'model_list')",
    "ll002_include_list": "'include' should be a list of file paths",
    "ll002_section_mapping": "'{section}' should be a mapping (key: value pairs), found {found}",
    "ll002_model_list": "'model_list' should be a list, found {found}",
    "ll002_entry_mapping": "{base} should be a mapping with model_name and litellm_params",
    "ll002_entry_no_name": "{base} has no model_name (clients could not call it)",
    "ll002_entry_no_params": "{base} has no litellm_params mapping",
    "ll002_entry_no_model": "{base}.litellm_params has no model (expected provider/model)",
    # --- LL101-LL104 -----------------------------------------------------
    "ll002_fb_where": "{where}: {what}",
    "fb_item_name": "item {i} should be a model name (text), found {found}",
    "fb_item_mapping": "item {i} should be a mapping like 'source-model: [fallback-model]', found {found}",
    "fb_source_text": "item {i} has a source that is not a model name (text)",
    "fb_target": "item {i} target {j} should be a model name (text), found {found}",
    "fb_maps_to_list": "item {i} should map to a list of model names, found {found}",
    "ll102": "fallback source group '{src}' in {where} is not a model_name in model_list",
    "ll101": "fallback target '{target}' in {where} is not a model_name in model_list{extra}{why}",
    "ll103": "model_group_alias '{name}' points at '{target}', which is not a model_name in model_list{extra}{why}",
    "ll104": "model_group_retry_policy group '{group}' is not a model_name in model_list",
    # --- LL201 -----------------------------------------------------------
    "src_process_env": "process environment",
    "src_config_env": "config environment_variables",
    "src_none": "no sources",
    "ll201_malformed": "malformed os.environ/ reference at {path} (expected os.environ/NAME; the text is not shown)",
    "ll201_kms": (
        "environment variable '{name}' not found in: {searched}; "
        "general_settings.key_management_system is set, so it may be read from the secret manager{extra}"
    ),
    "ll201_missing": "environment variable '{name}' not found in: {searched}{extra}",
    # --- LL202, LL301 ----------------------------------------------------
    "ll202": "'{path}' holds a literal secret (value not shown); use os.environ/NAME and keep the value outside the file",
    "reason_empty": "is empty",
    "reason_known": "is a publicly known example key",
    "ll301": (
        "general_settings.master_key {reason}; the proxy refuses to start with it "
        "unless {override} is true. Use os.environ/LITELLM_MASTER_KEY with a long random value"
    ),
    # --- LL401, LL402 ----------------------------------------------------
    "ll401": (
        "model_list[{i}] repeats model_list[{first}] exactly (same model_name and litellm_params); "
        "it only doubles that deployment's share of traffic"
    ),
    "ll402_hint": "provider prefix '{prefix}' in {path} is not a litellm provider (did you mean '{hint}'?)",
    "ll402_info": (
        "provider prefix '{prefix}' in {path} is not in the litellm provider list; "
        "fine if custom_llm_provider is set elsewhere"
    ),
}

KO: dict[str, str] = {
    # --- CLI -------------------------------------------------------------
    "cli_description": "LiteLLM 프록시 config.yaml 정적 검사 도구입니다(비공식). 프록시를 시작하거나 API 를 호출하지 않습니다.",
    "help_version": "버전과 스키마 스냅숏을 표시하고 종료합니다",
    "help_lang": "출력 언어: en 또는 ko (기본값: LITELLM_LINT_LANG, 그다음 LC_ALL/LC_MESSAGES/LANG, 그 밖에는 en)",
    "help_check": "설정 파일을 검사합니다 (종료 코드 0 문제 없음, 1 문제 발견, 2 사용법 또는 YAML 오류)",
    "help_config": "프록시 config.yaml 경로(여러 개 가능, 종료 코드는 가장 나쁜 값)",
    "help_env_file": "이름을 정의된 것으로 인정할 dotenv 파일(여러 번 지정 가능)",
    "help_no_os_env": "현재 프로세스 환경변수를 인정하지 않습니다",
    "help_strict": "경고만 있어도 종료 코드 1 로 끝냅니다",
    "help_ignore": "건너뛸 규칙 코드를 쉼표로 구분해 지정합니다(예: LL001,LL402)",
    "help_format": "출력 형식(기본값: text)",
    "help_schema": "편집기(yaml-language-server)용 JSON Schema 를 내보냅니다",
    "help_output": "표준 출력 대신 파일에 씁니다",
    "version_text": "litellm-lint {version} (스키마 스냅숏: litellm {snapshot})",
    "cli_error": "litellm-lint: 오류: {text}",
    "cli_no_command": "명령을 고르십시오: check 또는 schema (--help 참고)",
    "cli_unrecognized": "인식할 수 없는 인자입니다: {args}",
    "cli_internal_error": (
        "litellm-lint: 내부 오류({name})가 발생해 종료 코드 2 로 끝납니다. 오류를 재현하는 최소한의 설정 파일로 "
        "제보해 주십시오(비밀 값은 먼저 지우십시오)."
    ),
    "cli_wrote": "{path} 에 썼습니다",
    # --- report ----------------------------------------------------------
    "report_header": "litellm-lint {version} (스키마 스냅숏: litellm {snapshot}, 생성일 {generated})",
    "n_error_one": "오류 {n}건",
    "n_error_other": "오류 {n}건",
    "n_warning_one": "경고 {n}건",
    "n_warning_other": "경고 {n}건",
    "n_info_one": "정보 {n}건",
    "n_info_other": "정보 {n}건",
    "n_file_one": "파일 {n}개",
    "n_file_other": "파일 {n}개",
    "total_line": "합계: {files}, {errors}, {warnings}",
    "sev_error": "오류",
    "sev_warning": "경고",
    "sev_info": "정보",
    "sep_or": " 또는 ",
    "sep_comma": ", ",
    # --- shared words ----------------------------------------------------
    "kind_mapping": "매핑",
    "kind_list": "목록",
    "kind_boolean": "불리언",
    "kind_number": "숫자",
    "kind_text": "텍스트",
    "kind_empty": "빈 값",
    "type_string": "문자열",
    "type_number": "숫자",
    "type_integer": "정수",
    "type_boolean": "불리언",
    "type_object": "객체",
    "type_array": "배열",
    "did_you_mean": " ('{hint}' 을(를) 말씀하신 것입니까?)",
    "why_db": " (store_model_in_db 가 켜져 있어 경고로만 표시합니다)",
    "why_empty": " (model_list 가 비어 있거나 없어 경고로만 표시합니다)",
    # --- input problems (exit code 2) ------------------------------------
    "config_not_found": "설정 파일을 찾을 수 없습니다: {path}. 경로를 확인하거나 프로젝트 디렉터리에서 실행하십시오.",
    "config_unreadable": "{path} 을(를) UTF-8 텍스트로 읽을 수 없습니다 ({name}).",
    "env_file_not_found": "env 파일을 찾을 수 없습니다: {path}. --env-file 경로를 고치거나 옵션을 빼십시오.",
    "env_file_unreadable": "env 파일 {path} 을(를) 읽을 수 없습니다 ({name}).",
    "unknown_rule_code": "--ignore 에 알 수 없는 규칙 코드 {code!r} 이(가) 있습니다. 사용 가능한 코드: {known}",
    # --- LL900 -----------------------------------------------------------
    "yaml_cannot_parse": "YAML 을 해석할 수 없습니다: {what}",
    "yaml_duplicate_key": "중복된 키입니다(프록시는 마지막 값만 조용히 사용합니다)",
    "yaml_invalid_construct": "올바르지 않은 YAML 구문입니다",
    "yaml_too_deep": "중첩이 너무 깊습니다: 문서가 {limit}단계보다 깊게 중첩되어 있습니다",
    "yaml_too_big": "별칭 확장이 너무 많습니다: 문서가 {limit}개가 넘는 노드로 확장됩니다(YAML 별칭 폭탄일 수 있습니다)",
    "yaml_parser_gave_up": "중첩이 너무 깊습니다: 해석기가 포기했습니다(한도 {limit}단계)",
    "yaml_walk_too_deep": "중첩이 너무 깊습니다: 문서를 끝까지 순회할 수 없었습니다",
    "root_not_mapping": "설정의 최상위는 매핑(키: 값 쌍)이어야 합니다",
    "inc_unresolvable": "포함된 파일의 경로를 확인할 수 없습니다",
    "inc_too_many": "포함된 파일이 너무 많습니다(한도 {limit}개). include 연쇄가 끝없이 이어지고 있지 않습니까?",
    "inc_not_found": (
        "포함된 파일을 찾을 수 없습니다: {entry} (프록시가 시작되지 않습니다. 경로는 그 파일을 나열한 파일 기준 상대 경로입니다)"
    ),
    "inc_unreadable": "포함된 파일을 UTF-8 텍스트로 읽을 수 없습니다",
    "inc_not_mapping": "포함된 파일은 매핑(키: 값 쌍)이어야 합니다",
    "inc_bad_include": "포함된 파일의 'include' 는 파일 경로 목록이어야 합니다",
    # --- LL000 -----------------------------------------------------------
    "ll000": (
        "설치된 litellm {installed} 이(가) 스키마 스냅숏 {snapshot} 과(와) 다릅니다. "
        "새 버전에서 추가된 키는 알 수 없는 키로 보고될 수 있습니다"
    ),
    # --- LL001-LL003 -----------------------------------------------------
    "ll003_misplaced": (
        "'{key}' 은(는) 올바른 router_settings 키가 아닙니다. {target} 으로 옮기십시오 (이 오류가 나면 프록시가 시작되지 않습니다)"
    ),
    "ll001_wrong_section": "{section} 에 알 수 없는 키 '{key}' 가 있습니다. 이 키는 {names} 에 속합니다",
    "ll001_hint": "{section} 에 알 수 없는 키 '{key}' 가 있습니다 ('{hint}' 을(를) 말씀하신 것입니까?)",
    "ll001_param_info": "{section} 의 키 '{key}' 은(는) 일반적인 매개변수가 아닙니다. 프록시가 이를 제공자에게 그대로 전달합니다",
    "ll001_snapshot": (
        "{section} 에 알 수 없는 키 '{key}' 가 있습니다: litellm {version} 스냅숏에 없습니다 (더 새로운 설정이거나 오타일 수 있습니다)"
    ),
    "ll002_type": "'{path}' 은(는) {expected} 이어야 하는데 {found} 입니다",
    "ll002_key_not_text": "최상위 키가 텍스트가 아닙니다 (키는 'model_list' 같은 이름이어야 합니다)",
    "ll002_include_list": "'include' 는 파일 경로 목록이어야 합니다",
    "ll002_section_mapping": "'{section}' 은(는) 매핑(키: 값 쌍)이어야 하는데 {found} 입니다",
    "ll002_model_list": "'model_list' 는 목록이어야 하는데 {found} 입니다",
    "ll002_entry_mapping": "{base} 은(는) model_name 과 litellm_params 를 가진 매핑이어야 합니다",
    "ll002_entry_no_name": "{base} 에 model_name 이 없습니다 (클라이언트가 호출할 수 없습니다)",
    "ll002_entry_no_params": "{base} 에 litellm_params 매핑이 없습니다",
    "ll002_entry_no_model": "{base}.litellm_params 에 model 이 없습니다 (provider/model 형식이 필요합니다)",
    # --- LL101-LL104 -----------------------------------------------------
    "ll002_fb_where": "{where}: {what}",
    "fb_item_name": "{i}번째 항목은 모델 이름(텍스트)이어야 하는데 {found} 입니다",
    "fb_item_mapping": "{i}번째 항목은 'source-model: [fallback-model]' 같은 매핑이어야 하는데 {found} 입니다",
    "fb_source_text": "{i}번째 항목의 원본이 모델 이름(텍스트)이 아닙니다",
    "fb_target": "{i}번째 항목의 {j}번째 대상은 모델 이름(텍스트)이어야 하는데 {found} 입니다",
    "fb_maps_to_list": "{i}번째 항목은 모델 이름 목록으로 연결되어야 하는데 {found} 입니다",
    "ll102": "{where} 의 폴백 원본 그룹 '{src}' 이(가) model_list 의 model_name 에 없습니다",
    "ll101": "{where} 의 폴백 대상 '{target}' 이(가) model_list 의 model_name 에 없습니다{extra}{why}",
    "ll103": "model_group_alias '{name}' 이(가) '{target}' 을(를) 가리키지만 model_list 의 model_name 에 없습니다{extra}{why}",
    "ll104": "model_group_retry_policy 그룹 '{group}' 이(가) model_list 의 model_name 에 없습니다",
    # --- LL201 -----------------------------------------------------------
    "src_process_env": "프로세스 환경변수",
    "src_config_env": "설정의 environment_variables",
    "src_none": "확인할 출처 없음",
    "ll201_malformed": "{path} 의 os.environ/ 참조 형식이 올바르지 않습니다 (os.environ/NAME 형식이어야 합니다. 값은 표시하지 않습니다)",
    "ll201_kms": (
        "환경변수 '{name}' 을(를) 다음에서 찾을 수 없습니다: {searched}. "
        "general_settings.key_management_system 가 설정되어 있어 비밀 관리자에서 읽을 수도 있습니다{extra}"
    ),
    "ll201_missing": "환경변수 '{name}' 을(를) 다음에서 찾을 수 없습니다: {searched}{extra}",
    # --- LL202, LL301 ----------------------------------------------------
    "ll202": "'{path}' 에 비밀 값이 그대로 들어 있습니다 (값은 표시하지 않습니다). os.environ/NAME 을 쓰고 값은 파일 밖에 두십시오",
    "reason_empty": "이(가) 비어 있습니다",
    "reason_known": "이(가) 공개적으로 알려진 예시 키입니다",
    "ll301": (
        "general_settings.master_key {reason}. {override} 가 true 가 아니면 "
        "프록시가 이 값으로 시작되지 않습니다. 긴 무작위 값을 담은 os.environ/LITELLM_MASTER_KEY 를 쓰십시오"
    ),
    # --- LL401, LL402 ----------------------------------------------------
    "ll401": (
        "model_list[{i}] 이(가) model_list[{first}] 과(와) 완전히 같습니다 (model_name 과 litellm_params 가 같음). "
        "해당 배포의 트래픽 비중만 두 배로 만듭니다"
    ),
    "ll402_hint": "{path} 의 제공자 접두사 '{prefix}' 은(는) litellm 제공자가 아닙니다 ('{hint}' 을(를) 말씀하신 것입니까?)",
    "ll402_info": (
        "{path} 의 제공자 접두사 '{prefix}' 은(는) litellm 제공자 목록에 없습니다. "
        "custom_llm_provider 를 다른 곳에서 설정했다면 문제없습니다"
    ),
}

# argparse's own sentences. Keys are argparse's English message ids (the stdlib looks them
# up through gettext); anything not listed here stays English.
ARGPARSE_KO: dict[str, str] = {
    "usage: ": "사용법: ",
    "positional arguments": "위치 인자",
    "options": "옵션",
    "optional arguments": "옵션",
    "show this help message and exit": "이 도움말을 표시하고 종료합니다",
    "%(prog)s: error: %(message)s\n": "%(prog)s: 오류: %(message)s\n",
    "invalid choice: %(value)r (choose from %(choices)s)": "잘못된 선택입니다: %(value)r (다음 중에서 고르십시오: %(choices)s)",
    "the following arguments are required: %s": "다음 인자가 필요합니다: %s",
    "unrecognized arguments: %s": "인식할 수 없는 인자입니다: %s",
    "expected one argument": "인자가 하나 필요합니다",
    "expected at most one argument": "인자는 최대 하나만 받습니다",
    "expected at least one argument": "인자가 하나 이상 필요합니다",
    "ambiguous option: %(option)s could match %(matches)s": "모호한 옵션입니다: %(option)s 은(는) %(matches)s 와(과) 일치할 수 있습니다",
    "invalid %(type)s value: %(value)r": "잘못된 %(type)s 값입니다: %(value)r",
    "argument %(argument_name)s: %(message)s": "인자 %(argument_name)s: %(message)s",
    "unknown parser %(parser_name)r (choices: %(choices)s)": "알 수 없는 하위 명령 %(parser_name)r (선택지: %(choices)s)",
    "ignored explicit argument %r": "명시한 인자 %r 은(는) 무시되었습니다",
    "not allowed with argument %s": "인자 %s 와(과) 함께 쓸 수 없습니다",
    "one of the arguments %s is required": "다음 인자 중 하나가 필요합니다: %s",
}

TABLES: dict[str, dict[str, str]] = {"en": EN, "ko": KO}


class Joined:
    """Items joined with a language-specific separator (``sep_or`` or ``sep_comma``)."""

    def __init__(self, items: Sequence[Any], sep_key: str = "sep_comma") -> None:
        self.items = list(items)
        self.sep_key = sep_key


class Msg(str):
    """The English text of a message that also knows how to render itself in another language."""

    key: str
    args: Mapping[str, Any]

    def __new__(cls, key: str, args: Mapping[str, Any]) -> "Msg":
        obj = super().__new__(cls, render(key, args, "en"))
        obj.key = key
        obj.args = dict(args)
        return obj


def _arg(value: Any, lang: str) -> Any:
    if isinstance(value, Msg):
        return render(value.key, value.args, lang)
    if isinstance(value, Joined):
        sep = TABLES[lang].get(value.sep_key, EN[value.sep_key])
        return sep.join(str(_arg(v, lang)) for v in value.items)
    return value


def render(key: str, args: Mapping[str, Any], lang: str) -> str:
    """Format message ``key`` in ``lang`` (falls back to English for a missing key)."""
    template = TABLES.get(lang, EN).get(key) or EN[key]
    return template.format(**{name: _arg(value, lang) for name, value in args.items()})


def msg(key: str, /, **args: Any) -> Msg:
    """A message that reads as English everywhere and can be rendered in Korean on demand."""
    if key not in EN:
        raise KeyError(f"unknown message key: {key}")
    return Msg(key, args)


def localize(text: Any, lang: str) -> str:
    """Render ``text`` in ``lang`` if it came from :func:`msg`, else return it unchanged."""
    if isinstance(text, Msg):
        return render(text.key, text.args, lang)
    return str(text)


def t(lang: str, key: str, /, **args: Any) -> str:
    """Render a message straight to text in ``lang`` (for output built right where it is printed)."""
    return render(key, args, lang)


def plural(lang: str, noun: str, n: int) -> str:
    """'1 error' / '2 errors' (English) or '오류 2건' (Korean)."""
    return render(f"n_{noun}_{'one' if n == 1 else 'other'}", {"n": n}, lang)


def normalize(value: str | None) -> str | None:
    """'en' or 'ko' for an explicit value (``ko_KR.UTF-8`` counts as ko), else None."""
    if not value:
        return None
    low = value.strip().lower()
    for lang in LANGUAGES:
        if low == lang or low.startswith((lang + "_", lang + "-", lang + ".", lang + "@")):
            return lang
    return None


def _from_locale(environ: Mapping[str, str]) -> str:
    # POSIX order: the first non-empty one of these decides, even if it is not Korean
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = environ.get(name, "").strip()
        if value:
            return normalize(value) or DEFAULT_LANGUAGE
    return DEFAULT_LANGUAGE


def resolve_language(flag: str | None = None, environ: Mapping[str, str] | None = None) -> str:
    """``--lang`` > ``LITELLM_LINT_LANG`` > ``LC_ALL``/``LC_MESSAGES``/``LANG`` > English.

    An invalid value at one level is skipped, so a typo never hides the next level.
    """
    env = os.environ if environ is None else environ
    return normalize(flag) or normalize(env.get(ENV_VAR)) or _from_locale(env)


def prescan_lang_flag(argv: Sequence[str]) -> str | None:
    """The value of ``--lang`` anywhere in ``argv`` (last one wins), found before argparse runs."""
    found: str | None = None
    items = list(argv)
    for i, arg in enumerate(items):
        if arg == "--lang" and i + 1 < len(items):
            found = items[i + 1]
        elif arg.startswith("--lang="):
            found = arg.split("=", 1)[1]
    return found


@contextlib.contextmanager
def argparse_language(lang: str) -> Iterator[None]:
    """Translate argparse's own sentences (usage, headings, error texts) while parsing.

    The stdlib calls a module-level gettext function; swapping it for the length of one
    parse is the only hook it offers. Not thread-safe, which is fine for a CLI.
    """
    import argparse

    if lang != "ko":
        yield
        return
    original = argparse._  # type: ignore[attr-defined]
    original_n = getattr(argparse, "ngettext", None)

    def tr(message: str) -> str:
        return ARGPARSE_KO.get(message, original(message))

    def tr_n(singular: str, plural_: str, n: int) -> str:
        return ARGPARSE_KO.get(singular, original_n(singular, plural_, n) if original_n else singular)

    argparse._ = tr  # type: ignore[attr-defined]
    if original_n is not None:
        argparse.ngettext = tr_n  # type: ignore[attr-defined]
    try:
        yield
    finally:
        argparse._ = original  # type: ignore[attr-defined]
        if original_n is not None:
            argparse.ngettext = original_n  # type: ignore[attr-defined]
