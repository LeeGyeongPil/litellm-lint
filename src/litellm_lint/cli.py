"""Command line interface: ``litellm-lint check`` and ``litellm-lint schema``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__, report as report_mod
from .core import check_file
from .diagnostics import LintUsageError
from .i18n import DEFAULT_LANGUAGE, LANGUAGES, argparse_language, localize, prescan_lang_flag, resolve_language, t
from .schema_export import export_schema
from .snapshot import DEFAULT_LITELLM_VERSION


def version_text(lang: str = DEFAULT_LANGUAGE) -> str:
    return t(lang, "version_text", version=__version__, snapshot=DEFAULT_LITELLM_VERSION)


def _add_lang_option(parser: argparse.ArgumentParser, lang: str, *, top: bool) -> None:
    """--lang is accepted on the main parser and on every subcommand (``check --lang ko``).

    The value itself is read from argv before parsing (see ``main``) so that even the help
    text can be translated; the option is declared here for ``--help`` and validation.
    """
    kwargs = {} if top else {"default": argparse.SUPPRESS}
    parser.add_argument("--lang", choices=LANGUAGES, metavar="{en,ko}", help=t(lang, "help_lang"), **kwargs)


def build_parser(lang: str = DEFAULT_LANGUAGE) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="litellm-lint", description=t(lang, "cli_description"))
    parser.add_argument("--version", action="store_true", help=t(lang, "help_version"))
    _add_lang_option(parser, lang, top=True)
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help=t(lang, "help_check"))
    check.add_argument("config", nargs="+", help=t(lang, "help_config"))
    check.add_argument("--env-file", action="append", default=[], metavar="PATH", help=t(lang, "help_env_file"))
    check.add_argument("--no-os-env", action="store_true", help=t(lang, "help_no_os_env"))
    check.add_argument("--strict", action="store_true", help=t(lang, "help_strict"))
    check.add_argument("--ignore", action="append", default=[], metavar="CODES", help=t(lang, "help_ignore"))
    check.add_argument("--format", choices=("text", "json"), default="text", help=t(lang, "help_format"))
    _add_lang_option(check, lang, top=False)

    schema = sub.add_parser("schema", help=t(lang, "help_schema"))
    schema.add_argument("-o", "--output", metavar="PATH", help=t(lang, "help_output"))
    _add_lang_option(schema, lang, top=False)
    return parser


def _run_check(args: argparse.Namespace, lang: str) -> int:
    ignore = [c for part in args.ignore for c in part.split(",") if c.strip()]
    # check every file before printing, so a bad path (usage error) prints nothing half-way
    reports = [
        check_file(path, env_files=args.env_file, use_os_env=not args.no_os_env, ignore=ignore) for path in args.config
    ]
    if args.format == "json":
        # JSON is for machines: identical in every language
        print(report_mod.format_json(reports[0]) if len(reports) == 1 else report_mod.format_json_many(reports))
    elif len(reports) == 1:
        print(report_mod.format_text(reports[0], lang))
    else:
        print(report_mod.format_text_many(reports, lang))
    return max(2 if any(d.code == "LL900" for d in rep.diagnostics) else rep.exit_code(strict=args.strict) for rep in reports)


def _run_schema(args: argparse.Namespace, lang: str) -> int:
    # the JSON Schema is machine output and is never translated
    text = json.dumps(export_schema(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(t(lang, "cli_wrote", path=args.output))
    else:
        sys.stdout.write(text)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)
    # decide the language before argparse runs, so --help and parse errors are translated too
    lang = resolve_language(prescan_lang_flag(argv_list))
    with argparse_language(lang):
        return _main(argv_list, lang)


def _main(argv: list[str], lang: str) -> int:
    parser = build_parser(lang)
    args, extra = parser.parse_known_args(argv)
    if extra:
        # argparse stops collecting positionals after the first option; accept more files after it
        if args.command == "check" and not any(e.startswith("-") for e in extra):
            args.config += extra
        else:
            parser.error(t(lang, "cli_unrecognized", args=" ".join(extra)))
    if args.version:
        print(version_text(lang))
        return 0
    if args.command is None:
        parser.print_usage(sys.stderr)
        print(t(lang, "cli_error", text=t(lang, "cli_no_command")), file=sys.stderr)
        return 2
    try:
        return _run_check(args, lang) if args.command == "check" else _run_schema(args, lang)
    except LintUsageError as exc:
        print(t(lang, "cli_error", text=localize(exc.args[0], lang)), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - last line of defence; never print values from the file
        print(t(lang, "cli_internal_error", name=type(exc).__name__), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
