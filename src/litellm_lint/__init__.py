"""litellm-lint: static checks for LiteLLM proxy ``config.yaml`` (unofficial)."""
from __future__ import annotations

__version__ = "0.2.0"

from .core import check_file
from .diagnostics import Diagnostic, LintUsageError, Report, Severity
from .schema_export import export_schema

__all__ = [
    "__version__",
    "check_file",
    "export_schema",
    "Diagnostic",
    "Report",
    "Severity",
    "LintUsageError",
]
