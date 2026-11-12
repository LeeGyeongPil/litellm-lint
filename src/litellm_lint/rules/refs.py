"""LL101-LL104: references must point at a model_name that exists.

A "model group" is every ``model_list`` entry sharing one ``model_name``. Several entries
with the same name are load balancing, not an error. ``model_name`` may be a wildcard
pattern (``openai/*``, ``*``), and ``router_settings.model_group_alias`` adds extra names.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Any, Iterator

from ..context import Context
from ..diagnostics import Diagnostic, Severity
from ..i18n import msg
from ..loader import item_pos, key_pos, value_pos
from ..suggest import closest

_GLOB = "*?["


class ModelIndex:
    """Names the proxy can route: exact model_names, wildcard patterns, and aliases."""

    def __init__(self, config: Any, extra_models: list[Any] | None = None) -> None:
        self.names: set[str] = set()
        self.patterns: list[str] = []
        self.aliases: set[str] = set()
        models = config.get("model_list")
        for entry in [*(models if isinstance(models, list) else []), *(extra_models or [])]:
            name = entry.get("model_name") if isinstance(entry, dict) else None
            if isinstance(name, str) and name:
                if any(c in name for c in _GLOB):
                    self.patterns.append(name)
                else:
                    self.names.add(name)
        router = config.get("router_settings")
        alias = router.get("model_group_alias") if isinstance(router, dict) else None
        if isinstance(alias, dict):
            self.aliases = {str(k) for k in alias}
        self.has_models = bool(self.names or self.patterns)

    def group_exists(self, name: str) -> bool:
        return name in self.names or any(fnmatchcase(name, p) for p in self.patterns)

    def name_exists(self, name: str) -> bool:
        return self.group_exists(name) or name in self.aliases

    def all_names(self) -> set[str]:
        return self.names | self.aliases


def _target_name(target: Any) -> str | None:
    if isinstance(target, str):
        return target
    if isinstance(target, dict) and isinstance(target.get("model"), str):
        return target["model"]
    return None


def _fallback_entries(
    mapping: dict, key: str
) -> Iterator[tuple[str | None, tuple[int | None, int | None], str, tuple[int | None, int | None]]]:
    """Yield (source_group_or_None, source_pos, target_name, target_pos)."""
    value = mapping.get(key)
    if not isinstance(value, list):
        return
    for i, item in enumerate(value):
        if key == "default_fallbacks":
            name = _target_name(item)
            if name:
                yield None, (None, None), name, item_pos(value, i)
            continue
        if not isinstance(item, dict):
            continue
        for src, targets in item.items():
            src_pos = key_pos(item, src)
            if isinstance(targets, list):
                for j, target in enumerate(targets):
                    name = _target_name(target)
                    if name:
                        yield str(src), src_pos, name, item_pos(targets, j)
            else:
                name = _target_name(targets)
                if name:
                    yield str(src), src_pos, name, value_pos(item, src)


def _check_fallback_shapes(ctx: Context) -> list[Diagnostic]:
    """LL002 for fallback list elements that are not ``{source: [target, ...]}`` (or a target)."""
    out: list[Diagnostic] = []

    def bad(where: str, what: str, pos: tuple[int | None, int | None]) -> None:
        out.append(ctx.diag("LL002", Severity.ERROR, msg("ll002_fb_where", where=where, what=what), pos, None, where))

    for section in ("litellm_settings", "router_settings"):
        mapping = ctx.section(section)
        if not mapping:
            continue
        for key in ctx.snapshot["rules"]["fallback_keys"]:
            value = mapping.get(key)
            if not isinstance(value, list):
                continue  # not-a-list is reported by the key rules
            where = f"{section}.{key}"
            for i, item in enumerate(value):
                pos = item_pos(value, i)
                if key == "default_fallbacks":
                    if _target_name(item) is None:
                        bad(where, msg("fb_item_name", i=i, found=_kind_of(item)), pos)
                    continue
                if not isinstance(item, dict):
                    bad(where, msg("fb_item_mapping", i=i, found=_kind_of(item)), pos)
                    continue
                for src, targets in item.items():
                    src_pos = key_pos(item, src)
                    if not isinstance(src, str):
                        bad(where, msg("fb_source_text", i=i), src_pos)
                    if isinstance(targets, list):
                        for j, target in enumerate(targets):
                            if _target_name(target) is None:
                                bad(where, msg("fb_target", i=i, j=j, found=_kind_of(target)), item_pos(targets, j))
                    elif _target_name(targets) is None:
                        bad(where, msg("fb_maps_to_list", i=i, found=_kind_of(targets)), value_pos(item, src))
    return out


def _kind_of(value: Any) -> str:
    if isinstance(value, dict):
        return msg("kind_mapping")
    if isinstance(value, list):
        return msg("kind_list")
    if value is None:
        return msg("kind_empty")
    if isinstance(value, bool):
        return msg("kind_boolean")
    if isinstance(value, (int, float)):
        return msg("kind_number")
    return msg("kind_text")


def check(ctx: Context) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    index = ModelIndex(ctx.config, ctx.included_models)
    out.extend(_check_fallback_shapes(ctx))
    general = ctx.section("general_settings") or {}
    # models may be added at runtime from the database, so "missing" is only a warning there
    soft = general.get("store_model_in_db") is True or not index.has_models
    missing_sev = Severity.WARNING if soft else Severity.ERROR
    why = (
        msg("why_db")
        if general.get("store_model_in_db") is True
        else (msg("why_empty") if not index.has_models else "")
    )

    fallback_keys = ctx.snapshot["rules"]["fallback_keys"]
    for section in ("litellm_settings", "router_settings"):
        mapping = ctx.section(section)
        if not mapping:
            continue
        for key in fallback_keys:
            seen_src: set[str] = set()
            for src, src_pos, target, target_pos in _fallback_entries(mapping, key):
                where = f"{section}.{key}"
                if src is not None and src != "*" and src not in seen_src:
                    seen_src.add(src)
                    if not index.name_exists(src):
                        out.append(
                            ctx.diag(
                                "LL102",
                                Severity.WARNING,
                                msg("ll102", src=src, where=where),
                                src_pos,
                                closest(src, index.all_names()),
                                where,
                            )
                        )
                if not index.name_exists(target):
                    hint = closest(target, index.all_names())
                    extra = msg("did_you_mean", hint=hint) if hint else ""
                    out.append(
                        ctx.diag(
                            "LL101",
                            missing_sev,
                            msg("ll101", target=target, where=where, extra=extra, why=why),
                            target_pos,
                            hint,
                            where,
                        )
                    )

    router = ctx.section("router_settings") or {}
    alias = router.get("model_group_alias")
    if isinstance(alias, dict):
        for name, spec in alias.items():
            target = spec if isinstance(spec, str) else (spec.get("model") if isinstance(spec, dict) else None)
            if not isinstance(target, str) or index.group_exists(target):
                continue
            hint = closest(target, index.names)
            extra = msg("did_you_mean", hint=hint) if hint else ""
            pos = value_pos(alias, name)
            if isinstance(spec, dict):
                pos = value_pos(spec, "model")
            out.append(
                ctx.diag(
                    "LL103",
                    missing_sev,
                    msg("ll103", name=name, target=target, extra=extra, why=why),
                    pos,
                    hint,
                    "router_settings.model_group_alias",
                )
            )

    policy = router.get("model_group_retry_policy")
    if isinstance(policy, dict):
        for group in policy:
            if not index.name_exists(str(group)):
                out.append(
                    ctx.diag(
                        "LL104",
                        Severity.WARNING,
                        msg("ll104", group=group),
                        key_pos(policy, group),
                        closest(str(group), index.all_names()),
                        "router_settings.model_group_retry_policy",
                    )
                )
    return out
