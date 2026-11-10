"""Shared state handed to every rule."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .diagnostics import Diagnostic, Severity
from .loader import Pos


@dataclass
class Context:
    path: str
    config: Any
    snapshot: dict[str, Any]
    env_sources: list[tuple[str, frozenset[str]]] = field(default_factory=list)
    included_models: list[Any] = field(default_factory=list)  # model_list entries from include files

    def section(self, name: str) -> Any:
        """A top-level section if it is a mapping, else None (keys.py reports the bad shape)."""
        value = self.config.get(name)
        return value if isinstance(value, dict) else None

    def diag(
        self,
        code: str,
        severity: Severity,
        message: str,
        pos: Pos = (None, None),
        suggestion: str | None = None,
        key: str = "",
    ) -> Diagnostic:
        return Diagnostic(code, severity, message, self.path, pos[0], pos[1], suggestion, key)
