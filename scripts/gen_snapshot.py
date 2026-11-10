#!/usr/bin/env python3
"""Generate a litellm-lint schema snapshot from an installed ``litellm``.

Usage (needs Python 3.10-3.14 and ``litellm[proxy]`` installed)::

    uv run --isolated --python 3.12 --with "litellm[proxy]==1.108.4" \\
        python scripts/gen_snapshot.py --out src/litellm_lint/snapshots/

The result is ``litellm-<version>.json``.  It only contains key names, simple
types and provenance labels -- no litellm code or documentation strings.
Files under any path containing "enterprise" are never scanned (separate
licence).

The module is split in two on purpose:

* pure helpers (``scan_keys``, ``simplify_annotation`` ...) need no litellm and
  are unit-tested offline;
* ``build_snapshot`` imports litellm lazily and does the real extraction.
"""
from __future__ import annotations

import argparse
import ast
import datetime as _dt
import enum
import inspect
import json
import os
import sys
import types
import typing
from pathlib import Path
from typing import Any, Iterable

GENERATOR_VERSION = "1"

SIMPLE_TYPES = {
    bool: "boolean",
    int: "integer",
    float: "number",
    str: "string",
    list: "array",
    tuple: "array",
    set: "array",
    dict: "object",
}


# --------------------------------------------------------------------------
# Pure helpers (no litellm needed)
# --------------------------------------------------------------------------
def is_excluded_path(path: str | Path) -> bool:
    """True for files we must not read (enterprise code has another licence)."""
    return any("enterprise" in part.lower() for part in Path(path).parts)


def _str_const(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def scan_keys(source: str, receivers: Iterable[str]) -> set[str]:
    """Collect string keys a source file reads from the given mapping names.

    Recognised forms (``R`` is a name in ``receivers``)::

        R.get("k")   R.get("k", default)   R["k"]   "k" in R
        for key, value in R.items():  if key == "k" / key in ("a", "b")

    Returns an empty set if the source does not parse.
    """
    names = set(receivers)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: set[str] = set()

    def is_recv(node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id in names

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("get", "pop", "setdefault")
            and is_recv(node.func.value)
            and node.args
        ):
            k = _str_const(node.args[0])
            if k:
                found.add(k)
        elif isinstance(node, ast.Subscript) and is_recv(node.value):
            k = _str_const(node.slice)
            if k:
                found.add(k)
        elif (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], (ast.In, ast.NotIn))
            and is_recv(node.comparators[0])
        ):
            k = _str_const(node.left)
            if k:
                found.add(k)
        elif isinstance(node, ast.For):
            # for key, value in R.items(): ... key == "x"
            it = node.iter
            if (
                isinstance(it, ast.Call)
                and isinstance(it.func, ast.Attribute)
                and it.func.attr == "items"
                and is_recv(it.func.value)
                and isinstance(node.target, ast.Tuple)
                and node.target.elts
                and isinstance(node.target.elts[0], ast.Name)
            ):
                loop_var = node.target.elts[0].id
                for sub in ast.walk(node):
                    if (
                        isinstance(sub, ast.Compare)
                        and isinstance(sub.left, ast.Name)
                        and sub.left.id == loop_var
                    ):
                        for comp in sub.comparators:
                            k = _str_const(comp)
                            if k:
                                found.add(k)
                            elif isinstance(comp, (ast.Tuple, ast.List, ast.Set)):
                                for elt in comp.elts:
                                    k = _str_const(elt)
                                    if k:
                                        found.add(k)
    return found


def scan_tree(root: Path, receivers: Iterable[str], only: str | None = None) -> set[str]:
    """Run ``scan_keys`` over every .py file below ``root`` except enterprise paths."""
    keys: set[str] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if is_excluded_path(rel):
            continue
        if only is not None and rel.as_posix() != only:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        keys |= scan_keys(text, receivers)
    return keys


def simplify_annotation(ann: Any) -> dict[str, Any]:
    """Reduce a type annotation to ``{"type": [...], "enum": [...]?}``.

    ``"any"`` means "do not type-check" (unknown or too complex).
    """
    types_found: set[str] = set()
    enum_values: list[Any] = []
    unknown = False

    def visit(a: Any) -> None:
        nonlocal unknown
        origin = typing.get_origin(a)
        if a is None or a is type(None):
            types_found.add("null")
        elif a in SIMPLE_TYPES:
            types_found.add(SIMPLE_TYPES[a])
        elif origin in (typing.Union, getattr(types, "UnionType", object())):
            for arg in typing.get_args(a):
                visit(arg)
        elif origin is typing.Literal:
            for arg in typing.get_args(a):
                enum_values.append(arg)
                if isinstance(arg, bool):
                    types_found.add("boolean")
                elif isinstance(arg, int):
                    types_found.add("integer")
                elif isinstance(arg, str):
                    types_found.add("string")
                else:
                    unknown = True
        elif origin in SIMPLE_TYPES:
            types_found.add(SIMPLE_TYPES[origin])
        elif origin is not None and getattr(origin, "__name__", "") in ("Sequence", "Iterable"):
            types_found.add("array")
        elif origin is not None and getattr(origin, "__name__", "") in ("Mapping", "MutableMapping"):
            types_found.add("object")
        else:
            unknown = True

    visit(ann)
    if unknown or not types_found - {"null"}:
        return {"type": ["any"]}
    out: dict[str, Any] = {"type": sorted(types_found)}
    if enum_values and len(enum_values) == len(set(map(repr, enum_values))):
        out["enum"] = enum_values
    return out


def type_of_value(value: Any) -> str:
    """Single simple type name for a module attribute default."""
    if isinstance(value, bool):
        return "boolean"
    for py, name in SIMPLE_TYPES.items():
        if type(value) is py:
            return name
    return "any"


# --------------------------------------------------------------------------
# litellm-dependent extraction
# --------------------------------------------------------------------------
def _model_fields(model: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, field in sorted(model.model_fields.items()):
        out[name] = simplify_annotation(field.annotation)
    return out


def build_snapshot() -> dict[str, Any]:
    """Extract the snapshot from the litellm installed in this interpreter."""
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import importlib.metadata as md

    import litellm
    from litellm.constants import ROUTER_SETTINGS_MANAGED_OUTSIDE_CONFIG
    from litellm.proxy._types import ConfigGeneralSettings, ConfigYAML
    from litellm.proxy.auth import master_key_boot_check as mkc
    from litellm.proxy.common_utils.config_includes import INCLUDE_KEY
    from litellm.types.router import GenericLiteLLMParams, LiteLLM_Params

    version = md.version("litellm")
    proxy_dir = Path(litellm.__file__).parent / "proxy"
    proxy_server = "proxy_server.py"

    # --- top level: ConfigYAML fields + config.get("...") in proxy_server.py
    top: dict[str, dict[str, Any]] = {}
    for name in ConfigYAML.model_fields:
        top[name] = {"source": "pydantic:ConfigYAML"}
    for key in sorted(scan_tree(proxy_dir, ["config", "_config"], only=proxy_server)):
        top.setdefault(key, {"source": "ast:proxy_server.py config.get"})
    # the top-level include directive is read in common_utils/config_includes.py, not via config.get
    top.setdefault(INCLUDE_KEY, {"source": "constant:config_includes.INCLUDE_KEY"})

    # --- router_settings: Router.__init__ args - managed outside config
    sig = inspect.signature(litellm.Router.__init__)
    valid = set(litellm.Router.get_valid_args()) - set(ROUTER_SETTINGS_MANAGED_OUTSIDE_CONFIG)
    router: dict[str, dict[str, Any]] = {}
    for name in sorted(valid):
        param = sig.parameters.get(name)
        ann = param.annotation if param is not None and param.annotation is not inspect._empty else Any
        entry = simplify_annotation(ann)
        entry["source"] = "signature:Router.__init__"
        router[name] = entry

    # --- litellm_settings: module attributes + branch comparisons
    lset: dict[str, dict[str, Any]] = {}
    for name, value in sorted(vars(litellm).items()):
        if name.startswith("_") or inspect.ismodule(value) or callable(value):
            continue
        lset[name] = {"type": ["any"], "source": "module_attr", "default_type": type_of_value(value)}
    branch = scan_tree(proxy_dir, ["litellm_settings", "_litellm_settings"], only=proxy_server)
    for key in sorted(branch):
        lset.setdefault(key, {"type": ["any"], "source": "ast:proxy_server.py litellm_settings"})
    # integrations read their own keys from the litellm_settings mapping handed to them
    for key in sorted(scan_tree(Path(litellm.__file__).parent / "integrations", ["litellm_settings", "_litellm_settings"])):
        lset.setdefault(key, {"type": ["any"], "source": "ast:integrations litellm_settings"})

    # --- general_settings: model fields + AST scan of proxy/ (enterprise excluded)
    gen: dict[str, dict[str, Any]] = {}
    for name, entry in _model_fields(ConfigGeneralSettings).items():
        entry["source"] = "pydantic:ConfigGeneralSettings"
        gen[name] = entry
    for key in sorted(scan_tree(proxy_dir, ["general_settings", "_general_settings"])):
        gen.setdefault(key, {"type": ["any"], "source": "ast:proxy general_settings"})

    # --- litellm_params
    params: dict[str, dict[str, Any]] = {}
    for model in (GenericLiteLLMParams, LiteLLM_Params):
        for name, entry in _model_fields(model).items():
            entry["source"] = f"pydantic:{model.__name__}"
            params.setdefault(name, entry)

    # completion arguments (temperature, max_tokens ...) are also valid in litellm_params
    skip = {"messages", "model_list", "kwargs", "args"}
    for name in inspect.signature(litellm.completion).parameters:
        if name not in skip:
            params.setdefault(name, {"type": ["any"], "source": "signature:litellm.completion"})
    for name in getattr(litellm, "OPENAI_CHAT_COMPLETION_PARAMS", []):
        params.setdefault(name, {"type": ["any"], "source": "litellm.OPENAI_CHAT_COMPLETION_PARAMS"})

    providers = sorted({p.value if isinstance(p, enum.Enum) else str(p) for p in litellm.provider_list})

    rules = {
        "fallback_keys": [
            "fallbacks",
            "context_window_fallbacks",
            "content_policy_fallbacks",
            "default_fallbacks",
        ],
        # proxy_server.py raises ValueError for these two under router_settings
        "misplaced_router_settings": {
            "health_check_interval": "general_settings",
            "health_check_concurrency": "general_settings",
        },
        "master_key": {
            "source": "litellm/proxy/auth/master_key_boot_check.py master_key_boot_verdict",
            "refused_when": ["empty", "publicly_known"],
            "publicly_known_sha256": sorted(mkc.PUBLICLY_KNOWN_MASTER_KEY_SHA256_DIGESTS),
            "override_setting": mkc.WEAK_OR_UNSET_MASTER_KEY_OVERRIDE_SETTING,
            "override_env_var": mkc.WEAK_OR_UNSET_MASTER_KEY_OVERRIDE_ENV_VAR,
        },
    }

    return {
        "meta": {
            "litellm_version": version,
            "python_version": ".".join(map(str, sys.version_info[:3])),
            "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d"),
            "generator_version": GENERATOR_VERSION,
            "licence_note": "Key names and simple types only; litellm is MIT licensed, enterprise/ paths are never read.",
            "sources": [
                "litellm.proxy._types.ConfigYAML / ConfigGeneralSettings (pydantic fields)",
                "litellm.Router.__init__ signature minus constants.ROUTER_SETTINGS_MANAGED_OUTSIDE_CONFIG",
                "public non-callable attributes of the litellm module",
                "AST scan of litellm/proxy/*.py for config.get / general_settings.get / litellm_settings branches",
                "AST scan of litellm/integrations/ (enterprise excluded) for litellm_settings[...] / .get reads",
                "litellm.proxy.common_utils.config_includes.INCLUDE_KEY (top-level include directive)",
                "litellm.types.router.LiteLLM_Params / GenericLiteLLMParams (pydantic fields)",
                "litellm.completion signature and litellm.OPENAI_CHAT_COMPLETION_PARAMS (names only)",
                "litellm.provider_list (enum values)",
            ],
        },
        "top_level": dict(sorted(top.items())),
        "router_settings": router,
        "litellm_settings": lset,
        "general_settings": dict(sorted(gen.items())),
        "litellm_params": dict(sorted(params.items())),
        "providers": providers,
        "rules": rules,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a litellm-lint schema snapshot.")
    parser.add_argument("--out", required=True, help="output directory (file: litellm-<version>.json)")
    args = parser.parse_args(argv)
    try:
        snap = build_snapshot()
    except ImportError as exc:
        print(
            f"error: cannot import litellm ({exc}). Run this script inside an environment with "
            '"litellm[proxy]" installed (Python 3.10-3.14), see the module docstring.',
            file=sys.stderr,
        )
        return 2
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"litellm-{snap['meta']['litellm_version']}.json"
    target.write_text(json.dumps(snap, indent=1, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")
    counts = {k: len(snap[k]) for k in ("top_level", "router_settings", "litellm_settings", "general_settings", "litellm_params", "providers")}
    print(f"wrote {target} {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
