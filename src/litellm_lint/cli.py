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
from .schema_export import export_schema
from .snapshot import DEFAULT_LITELLM_VERSION


def version_text() -> str:
    return f"litellm-lint {__version__} (schema snapshot: litellm {DEFAULT_LITELLM_VERSION})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="litellm-lint",
        description="Static checks for LiteLLM proxy config.yaml (unofficial). Does not start the proxy or call any API.",
    )
    parser.add_argument("--version", action="store_true", help="show version and schema snapshot, then exit")
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="check a config file (exit 0 clean, 1 findings, 2 usage or YAML error)")
    check.add_argument("config", nargs="+", help="path(s) to the proxy config.yaml (several files: exit code is the worst one)")
    check.add_argument("--env-file", action="append", default=[], metavar="PATH", help="dotenv file whose names count as defined (repeatable)")
    check.add_argument("--no-os-env", action="store_true", help="do not count the current process environment")
    check.add_argument("--strict", action="store_true", help="exit 1 on warnings too")
    check.add_argument("--ignore", action="append", default=[], metavar="CODES", help="comma-separated rule codes to skip, e.g. LL001,LL402")
    check.add_argument("--format", choices=("text", "json"), default="text")

    schema = sub.add_parser("schema", help="export a JSON Schema for editors (yaml-language-server)")
    schema.add_argument("-o", "--output", metavar="PATH", help="write to a file instead of stdout")
    return parser


def _run_check(args: argparse.Namespace) -> int:
    ignore = [c for part in args.ignore for c in part.split(",") if c.strip()]
    # check every file before printing, so a bad path (usage error) prints nothing half-way
    reports = [
        check_file(path, env_files=args.env_file, use_os_env=not args.no_os_env, ignore=ignore) for path in args.config
    ]
    if args.format == "json":
        print(report_mod.format_json(reports[0]) if len(reports) == 1 else report_mod.format_json_many(reports))
    else:
        print(report_mod.format_text(reports[0]) if len(reports) == 1 else report_mod.format_text_many(reports))
    return max(2 if any(d.code == "LL900" for d in rep.diagnostics) else rep.exit_code(strict=args.strict) for rep in reports)


def _run_schema(args: argparse.Namespace) -> int:
    text = json.dumps(export_schema(), indent=2, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if extra:
        # argparse stops collecting positionals after the first option; accept more files after it
        if args.command == "check" and not any(e.startswith("-") for e in extra):
            args.config += extra
        else:
            parser.error("unrecognized arguments: " + " ".join(extra))
    if args.version:
        print(version_text())
        return 0
    if args.command is None:
        parser.print_usage(sys.stderr)
        print("litellm-lint: error: choose a command: check or schema (see --help)", file=sys.stderr)
        return 2
    try:
        return _run_check(args) if args.command == "check" else _run_schema(args)
    except LintUsageError as exc:
        print(f"litellm-lint: error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - last line of defence; never print values from the file
        print(
            f"litellm-lint: internal error ({type(exc).__name__}); exit 2. Please report it with a minimal config "
            "that triggers it (remove secrets first).",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
