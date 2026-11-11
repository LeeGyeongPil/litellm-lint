"""Text and JSON output."""
from __future__ import annotations

import json
from typing import Any

from . import __version__
from .diagnostics import Report


def header(report: Report) -> str:
    return (
        f"litellm-lint {__version__} (schema snapshot: litellm {report.snapshot_version}, "
        f"generated {report.snapshot_generated_at})"
    )


def _count(n: int, word: str) -> str:
    """'1 error' but '0 errors' / '2 errors'."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def summary(report: Report) -> str:
    text = f"{_count(report.errors, 'error')}, {_count(report.warnings, 'warning')}"
    if report.infos:
        text += f", {report.infos} info"
    return text


def format_text(report: Report) -> str:
    lines = [header(report)]
    for d in report.sorted():
        where = d.path
        if d.line is not None:
            where += f":{d.line}:{d.col or 1}"
        lines.append(f"{where}: {d.severity.value} {d.code} {d.message}")
    lines.append(summary(report))
    return "\n".join(lines)


def format_text_many(reports: list[Report]) -> str:
    """Several files: one header, each file's findings and summary line, then a total."""
    lines = [header(reports[0])]
    for report in reports:
        lines.extend(format_text(report).splitlines()[1:-1])
        lines.append(f"{report.path}: {summary(report)}")
    errors = sum(r.errors for r in reports)
    warnings = sum(r.warnings for r in reports)
    lines.append(f"total: {len(reports)} files, {_count(errors, 'error')}, {_count(warnings, 'warning')}")
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
