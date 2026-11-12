"""LL001 unknown keys, LL002 types and shapes, LL003 misplaced keys."""
from __future__ import annotations

import re
from typing import Any

from ..context import Context
from ..diagnostics import Diagnostic, Severity
from ..i18n import EN, Joined, msg
from ..includes import include_entries
from ..loader import item_pos, key_pos, value_pos
from ..suggest import closest

ENV_REF = re.compile(r"^os\.environ/")
SECTIONS = ("router_settings", "general_settings", "litellm_settings")
NUMBER_TEXT = re.compile(r"^[+-]?\d+(\.\d+)?$")
BOOL_TEXT = {"true", "false", "yes", "no", "on", "off", "1", "0"}


def _snapshot_keys(snap: dict[str, Any], section: str) -> dict[str, Any]:
    return snap.get(section, {})


def type_problem(value: Any, allowed: list[str]) -> str | None:
    """Return the expected-type text (English) if ``value`` clearly does not fit, else None.

    Lenient on purpose: scalars may stand in for strings, numeric text for numbers,
    ``os.environ/NAME`` for anything, and an empty value (None) for anything.
    """
    if "any" in allowed or value is None:
        return None
    if isinstance(value, str) and ENV_REF.match(value):
        return None
    want = [t for t in allowed if t != "null"]
    if not want:
        return None
    if isinstance(value, dict):
        ok = "object" in want
    elif isinstance(value, list):
        ok = "array" in want
    elif isinstance(value, bool):
        ok = "boolean" in want or "string" in want
    elif isinstance(value, (int, float)):
        ok = "string" in want or "number" in want or ("integer" in want and float(value).is_integer())
    elif isinstance(value, str):
        ok = (
            "string" in want
            or (("integer" in want or "number" in want) and bool(NUMBER_TEXT.match(value.strip())))
            or ("boolean" in want and value.strip().lower() in BOOL_TEXT)
        )
    else:  # dates etc. are text in YAML
        ok = "string" in want
    return None if ok else " or ".join(want)


def _expected_msg(expected: str) -> Joined:
    """The 'string or number' part of an LL002 message, so it can be shown in either language."""
    names = []
    for word in expected.split(" or "):
        key = f"type_{word}"
        names.append(msg(key) if key in EN else word)
    return Joined(names, "sep_or")


def _check_unknown_key(
    ctx: Context, section: str, key: str, mapping: dict, known: dict[str, Any], key_path: str
) -> list[Diagnostic]:
    snap = ctx.snapshot
    version = snap["meta"]["litellm_version"]
    pos = key_pos(mapping, key)
    # LL003: keys the proxy explicitly rejects in router_settings
    if section == "router_settings":
        target = snap["rules"]["misplaced_router_settings"].get(key)
        if target:
            return [
                ctx.diag(
                    "LL003",
                    Severity.ERROR,
                    msg("ll003_misplaced", key=key, target=target),
                    pos,
                    target,
                    key_path,
                )
            ]
    if section != "litellm_params":
        others = [s for s in SECTIONS if s != section and key in _snapshot_keys(snap, s)]
        if others:
            names = " or ".join(others)  # suggestion text (stays English, machine readable)
            return [
                ctx.diag(
                    "LL001",
                    Severity.ERROR,
                    msg("ll001_wrong_section", key=key, section=section, names=Joined(others, "sep_or")),
                    pos,
                    names,
                    key_path,
                )
            ]
    hint = closest(key, known)
    if section == "litellm_params":
        if hint:
            return [
                ctx.diag(
                    "LL001",
                    Severity.WARNING,
                    msg("ll001_hint", key=key, section=section, hint=hint),
                    pos,
                    hint,
                    key_path,
                )
            ]
        return [
            ctx.diag(
                "LL001",
                Severity.INFO,
                msg("ll001_param_info", key=key, section=section),
                pos,
                None,
                key_path,
            )
        ]
    if hint:
        return [ctx.diag("LL001", Severity.ERROR, msg("ll001_hint", key=key, section=section, hint=hint), pos, hint, key_path)]
    return [
        ctx.diag(
            "LL001",
            Severity.WARNING,
            msg("ll001_snapshot", key=key, section=section, version=version),
            pos,
            None,
            key_path,
        )
    ]


def _check_mapping(ctx: Context, section: str, mapping: dict, known: dict[str, Any], prefix: str) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    fallback_keys = set(ctx.snapshot["rules"]["fallback_keys"])
    for key in list(mapping):
        if not isinstance(key, str):
            continue
        key_path = f"{prefix}.{key}" if prefix else key
        if key not in known:
            out.extend(_check_unknown_key(ctx, section, key, mapping, known, key_path))
            continue
        if section == "top_level":
            continue  # shapes of the sections are checked in check()
        if section == "litellm_settings":
            # setattr() target with no reliable type -- except the fallback lists
            allowed = ["array"] if key in fallback_keys else ["any"]
        else:
            allowed = list(known[key].get("type", ["any"]))
        expected = type_problem(mapping[key], allowed)
        if expected:
            out.append(
                ctx.diag(
                    "LL002",
                    Severity.ERROR,
                    msg("ll002_type", path=key_path, expected=_expected_msg(expected), found=_kind(mapping[key])),
                    value_pos(mapping, key),
                    None,
                    key_path,
                )
            )
    return out


def _kind(value: Any) -> str:
    if isinstance(value, dict):
        return msg("kind_mapping")
    if isinstance(value, list):
        return msg("kind_list")
    if isinstance(value, bool):
        return msg("kind_boolean")
    if isinstance(value, (int, float)):
        return msg("kind_number")
    return msg("kind_text")


def check(ctx: Context) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    snap = ctx.snapshot
    cfg = ctx.config

    out.extend(_check_mapping(ctx, "top_level", cfg, snap["top_level"], ""))

    for key in list(cfg):
        if not isinstance(key, str):
            out.append(ctx.diag("LL002", Severity.ERROR, msg("ll002_key_not_text"), key_pos(cfg, key), None, str(key)))
    if include_entries(cfg) is None:
        out.append(ctx.diag("LL002", Severity.ERROR, msg("ll002_include_list"), value_pos(cfg, "include"), None, "include"))

    for section in SECTIONS + ("environment_variables",):
        if section in cfg and cfg[section] is not None and not isinstance(cfg[section], dict):
            out.append(
                ctx.diag(
                    "LL002",
                    Severity.ERROR,
                    msg("ll002_section_mapping", section=section, found=_kind(cfg[section])),
                    value_pos(cfg, section),
                    None,
                    section,
                )
            )
    for section in SECTIONS:
        mapping = ctx.section(section)
        if mapping:
            out.extend(_check_mapping(ctx, section, mapping, snap[section], section))

    # model_list entries
    models = cfg.get("model_list")
    if models is not None and not isinstance(models, list):
        out.append(
            ctx.diag("LL002", Severity.ERROR, msg("ll002_model_list", found=_kind(models)), value_pos(cfg, "model_list"), None, "model_list")
        )
    elif isinstance(models, list):
        for i, entry in enumerate(models):
            base = f"model_list[{i}]"
            pos = item_pos(models, i)
            if not isinstance(entry, dict):
                out.append(ctx.diag("LL002", Severity.ERROR, msg("ll002_entry_mapping", base=base), pos, None, base))
                continue
            if not isinstance(entry.get("model_name"), str) or not entry.get("model_name"):
                out.append(ctx.diag("LL002", Severity.ERROR, msg("ll002_entry_no_name", base=base), pos, None, base))
            params = entry.get("litellm_params")
            if not isinstance(params, dict):
                out.append(ctx.diag("LL002", Severity.ERROR, msg("ll002_entry_no_params", base=base), pos, None, base))
                continue
            if not isinstance(params.get("model"), str) or not params.get("model"):
                out.append(ctx.diag("LL002", Severity.ERROR, msg("ll002_entry_no_model", base=base), key_pos(entry, "litellm_params"), None, f"{base}.litellm_params"))
            out.extend(_check_mapping(ctx, "litellm_params", params, snap["litellm_params"], f"{base}.litellm_params"))
    return out
