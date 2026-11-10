"""LL202 literal secrets, LL301 master_key values the proxy refuses to start with.

Values are inspected but never copied into a message.
"""
from __future__ import annotations

import hashlib

from ..context import Context
from ..diagnostics import Diagnostic, Severity
from ..loader import iter_scalars, value_pos

_EXACT = {"api_key", "master_key", "salt_key", "password", "secret", "token"}
_SUFFIXES = ("_api_key", "_password", "_secret", "_secret_key", "_secret_access_key", "_token", "_passwd")


def looks_secret(name: str) -> bool:
    low = name.lower()
    return low in _EXACT or low.endswith(_SUFFIXES)


def check(ctx: Context) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    general = ctx.section("general_settings") or {}
    rule = ctx.snapshot["rules"]["master_key"]
    weak_ok = general.get(rule["override_setting"]) is True

    weak_key_path = None
    master = general.get("master_key")
    if isinstance(master, str) and not master.startswith("os.environ/"):
        digest = hashlib.sha256(master.encode("utf-8")).hexdigest()
        reason = None
        if not master.strip():
            reason = "is empty"
        elif digest in rule["publicly_known_sha256"]:
            reason = "is a publicly known example key"
        if reason:
            weak_key_path = "general_settings.master_key"
            out.append(
                ctx.diag(
                    "LL301",
                    Severity.WARNING if weak_ok else Severity.ERROR,
                    f"general_settings.master_key {reason}; the proxy refuses to start with it "
                    f"unless {rule['override_setting']} is true. Use os.environ/LITELLM_MASTER_KEY with a long random value",
                    value_pos(general, "master_key"),
                    "os.environ/LITELLM_MASTER_KEY",
                    "general_settings.master_key",
                )
            )

    for key_path, last, value, pos in iter_scalars(ctx.config):
        if key_path == weak_key_path:
            continue
        if not isinstance(value, str) or not value.strip() or value.startswith("os.environ/"):
            continue
        if looks_secret(last):
            out.append(
                ctx.diag(
                    "LL202",
                    Severity.WARNING,
                    f"'{key_path}' holds a literal secret (value not shown); use os.environ/NAME and keep the value outside the file",
                    pos,
                    None,
                    key_path,
                )
            )
    return out
