"""Text and JSON output."""
from __future__ import annotations

import json
from typing import Any

from . import __version__
from .diagnostics import Report
from .i18n import DEFAULT_LANGUAGE, localize, plural, t


def header(report: Report, lang: str = DEFAULT_LANGUAGE) -> str:
    return t(
        lang,
        "report_header",
        version=__version__,
        snapshot=report.snapshot_version,
        generated=report.snapshot_generated_at,
    )


def _count(n: int, noun: str, lang: str = DEFAULT_LANGUAGE) -> str:
    """'1 error' but '0 errors' / '2 errors' (Korean has no plural: '오류 2건')."""
    return plural(lang, noun, n)


def summary(report: Report, lang: str = DEFAULT_LANGUAGE) -> str:
    text = f"{_count(report.errors, 'error', lang)}, {_count(report.warnings, 'warning', lang)}"
    if report.infos:
        text += f", {_count(report.infos, 'info', lang)}"
    return text


def format_text(report: Report, lang: str = DEFAULT_LANGUAGE) -> str:
    lines = [header(report, lang)]
    for d in report.sorted():
        where = d.path
        if d.line is not None:
            where += f":{d.line}:{d.col or 1}"
        severity = t(lang, f"sev_{d.severity.value}")
        lines.append(f"{where}: {severity} {d.code} {localize(d.message, lang)}")
    lines.append(summary(report, lang))
    return "\n".join(lines)


def format_text_many(reports: list[Report], lang: str = DEFAULT_LANGUAGE) -> str:
    """Several files: one header, each file's findings and summary line, then a total."""
    lines = [header(reports[0], lang)]
    for report in reports:
        lines.extend(format_text(report, lang).splitlines()[1:-1])
        lines.append(f"{report.path}: {summary(report, lang)}")
    errors = sum(r.errors for r in reports)
    warnings = sum(r.warnings for r in reports)
    lines.append(
        t(
            lang,
            "total_line",
            files=plural(lang, "file", len(reports)),
            errors=_count(errors, "error", lang),
            warnings=_count(warnings, "warning", lang),
        )
    )
    return "\n".join(lines)


def to_dict(report: Report) -> dict[str, Any]:
    return {
        "tool": "litellm-lint",
        "version": __version__,
        "snapshot": {
            "litellm_version": report.snapshot_version,
            "generated_at": report.snapshot_generated_at,
        },
        "file": report.path,
        "summary": {"errors": report.errors, "warnings": report.warnings, "info": report.infos},
        "diagnostics": [d.as_dict() for d in report.sorted()],
    }


def format_json(report: Report) -> str:
    return json.dumps(to_dict(report), indent=2, ensure_ascii=False)


def format_json_many(reports: list[Report]) -> str:
    """Several files: a JSON array with one report object per file, in argument order."""
    return json.dumps([to_dict(r) for r in reports], indent=2, ensure_ascii=False)
