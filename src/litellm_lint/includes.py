"""Top-level ``include:`` support (litellm merges the listed files into the main config).

Only what the reference rules need is taken from included files: their ``model_list`` entries,
so a fallback that points at a model defined in an included file is not a dangling reference.
Included files are not linted themselves. Like the proxy, each file is read once (so include
cycles end quietly) and a path is resolved next to the file that declares it, falling back to
the directory of the main config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .diagnostics import LintUsageError
from .i18n import msg
from .loader import _problem, parse_yaml_file

INCLUDE_KEY = "include"
MAX_INCLUDED_FILES = 50


def include_entries(config: Any) -> list[str] | None:
    """The include list, ``[]`` if absent, ``None`` if it is not a list of strings."""
    if not isinstance(config, dict) or INCLUDE_KEY not in config:
        return []
    entries = config[INCLUDE_KEY]
    if isinstance(entries, list) and all(isinstance(e, str) for e in entries):
        return [str(e) for e in entries]
    return None


def _resolve(entry: str, declared_in: Path, root: Path) -> Path:
    declared = declared_in.parent / entry
    if declared.exists():
        return declared
    fallback = root.parent / entry
    return fallback if fallback.exists() else declared


def collect_included_models(config: Any, root: Path) -> list[Any]:
    """``model_list`` entries from every file reachable through ``include``.

    Raises ``YamlProblem`` (LL900) when an included file is missing, unreadable, not a mapping,
    has a malformed ``include`` or the chain is longer than ``MAX_INCLUDED_FILES``.
    A malformed ``include`` in the main file is reported by the key rules (LL002), not here.
    """
    models: list[Any] = []
    seen = {root.resolve()}
    pending = [(entry, root) for entry in (include_entries(config) or [])]
    while pending:
        entry, declared_in = pending.pop(0)
        target = _resolve(entry, declared_in, root)
        shown = str(target)
        try:
            resolved = target.resolve()
        except OSError:
            raise _problem(msg("inc_unresolvable"), shown) from None
        if resolved in seen:
            continue  # the proxy reads each file once
        if len(seen) > MAX_INCLUDED_FILES:
            raise _problem(msg("inc_too_many", limit=MAX_INCLUDED_FILES), root)
        seen.add(resolved)
        if not target.is_file():
            raise _problem(msg("inc_not_found", entry=entry), declared_in)
        try:
            data = parse_yaml_file(target)
        except LintUsageError:
            raise _problem(msg("inc_unreadable"), shown) from None
        if not isinstance(data, dict):
            raise _problem(msg("inc_not_mapping"), shown)
        nested = include_entries(data)
        if nested is None:
            raise _problem(msg("inc_bad_include"), shown)
        listed = data.get("model_list")
        if isinstance(listed, list):
            models.extend(listed)
        pending.extend((e, target) for e in nested)
    return models


