"""Diagnostics: what a rule reports, and the report that collects them."""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Iterable


class LintUsageError(Exception):
    """Bad input from the caller (missing file, unreadable env file ...). CLI exit code 2."""


class Severity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# code -> (default severity, one-line title). Keep in sync with docs/rules.md.
RULES: dict[str, tuple[Severity, str]] = {
    "LL000": (Severity.INFO, "installed litellm differs from the schema snapshot"),
    "LL001": (Severity.ERROR, "unknown key"),
    "LL002": (Severity.ERROR, "wrong type or shape"),
    "LL003": (Severity.ERROR, "key is in the wrong section"),
    "LL101": (Severity.ERROR, "fallback target is not a model_name"),
    "LL102": (Severity.WARNING, "fallback source group is not a model_name"),
    "LL103": (Severity.ERROR, "model_group_alias target is not a model_name"),
    "LL104": (Severity.WARNING, "model_group_retry_policy group is not a model_name"),
    "LL201": (Severity.ERROR, "os.environ/ variable not found"),
    "LL202": (Severity.WARNING, "literal secret in config"),
    "LL301": (Severity.ERROR, "master_key the proxy refuses"),
    "LL401": (Severity.WARNING, "identical deployment repeated"),
    "LL402": (Severity.WARNING, "unknown provider prefix"),
    "LL900": (Severity.ERROR, "YAML could not be parsed"),
}


@dataclass(frozen=True)
class Diagnostic:
    """One finding. ``message`` is built from key names only -- never from values."""

    code: str
    severity: Severity
    message: str
    path: str
    line: int | None = None
    col: int | None = None
    suggestion: str | None = None
    key: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "file": self.path,
            "line": self.line,
            "column": self.col,
            "key": self.key,
            "suggestion": self.suggestion,
        }


@dataclass
class Report:
    """Result of checking one file."""

    path: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    snapshot_version: str = ""
    snapshot_generated_at: str = ""

    def count(self, severity: Severity) -> int:
        return sum(1 for d in self.diagnostics if d.severity is severity)

    @property
    def errors(self) -> int:
        return self.count(Severity.ERROR)

    @property
    def warnings(self) -> int:
        return self.count(Severity.WARNING)

    @property
    def infos(self) -> int:
        return self.count(Severity.INFO)

    def exit_code(self, strict: bool = False) -> int:
        """0 clean, 1 errors (or warnings when ``strict``)."""
        if self.errors or (strict and self.warnings):
            return 1
        return 0

    def sorted(self) -> list[Diagnostic]:
        return sorted(self.diagnostics, key=lambda d: (d.line or 0, d.col or 0, d.code))


def apply_ignore(diags: Iterable[Diagnostic], ignore: Iterable[str]) -> list[Diagnostic]:
    codes = {c.strip().upper() for c in ignore if c.strip()}
    return [d for d in diags if d.code not in codes]


def validate_codes(codes: Iterable[str]) -> None:
    for code in codes:
        if code.strip().upper() not in RULES:
            raise LintUsageError(
                f"unknown rule code {code!r} in --ignore; known codes: {', '.join(sorted(RULES))}"
            )
