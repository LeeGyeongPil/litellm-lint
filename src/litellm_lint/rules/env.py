"""LL201: ``os.environ/NAME`` references that no source defines. Only names are handled, never values."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from ..context import Context
from ..diagnostics import Diagnostic, LintUsageError, Severity
from ..i18n import Joined, msg
from ..loader import iter_scalars
from ..suggest import closest

PREFIX = "os.environ/"
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_DOTENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=")


def dotenv_names(path: Path) -> frozenset[str]:
    """Names defined in a dotenv file. Values are not read into memory beyond the line scan."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise LintUsageError(msg("env_file_not_found", path=path)) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise LintUsageError(msg("env_file_unreadable", path=path, name=type(exc).__name__)) from None
    names = set()
    for line in text.splitlines():
        match = _DOTENV_LINE.match(line)
        if match and not line.lstrip().startswith("#"):
            names.add(match.group(1))
    return frozenset(names)


def build_sources(env_files: Iterable[Path], use_os_env: bool) -> list[tuple[str, frozenset[str]]]:
    sources = [(str(p), dotenv_names(p)) for p in env_files]
    if use_os_env:
        sources.append((msg("src_process_env"), frozenset(os.environ)))
    return sources


def check(ctx: Context) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    general = ctx.section("general_settings") or {}
    uses_kms = bool(general.get("key_management_system"))
    config_env = ctx.section("environment_variables") or {}
    sources = list(ctx.env_sources)
    if config_env:
        sources.append((msg("src_config_env"), frozenset(str(k) for k in config_env)))
    known = set().union(*(names for _, names in sources)) if sources else set()
    labels = [label for label, _ in sources]
    searched = Joined(labels, "sep_comma") if labels else msg("src_none")

    for key_path, _last, value, pos in iter_scalars(ctx.config):
        if not isinstance(value, str) or not value.startswith(PREFIX):
            continue
        name = value[len(PREFIX):]
        if not _NAME.match(name):
            out.append(
                ctx.diag(
                    "LL201",
                    Severity.ERROR,
                    msg("ll201_malformed", path=key_path),
                    pos,
                    key=key_path,
                )
            )
            continue
        if name in known:
            continue
        hint = closest(name, known, cutoff=0.8)
        extra = msg("did_you_mean", hint=hint) if hint else ""
        if uses_kms:
            out.append(
                ctx.diag(
                    "LL201",
                    Severity.INFO,
                    msg("ll201_kms", name=name, searched=searched, extra=extra),
                    pos,
                    hint,
                    key_path,
                )
            )
        else:
            out.append(
                ctx.diag(
                    "LL201",
                    Severity.ERROR,
                    msg("ll201_missing", name=name, searched=searched, extra=extra),
                    pos,
                    hint,
                    key_path,
                )
            )
    return out
