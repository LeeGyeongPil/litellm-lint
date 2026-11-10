"""AC-8: the built-in snapshot and the generator script."""
from __future__ import annotations

import importlib.util
import json
import os
from typing import Literal, Optional, Union

import pytest

from litellm_lint.snapshot import load_snapshot

from conftest import ROOT

SNAPSHOT_FILE = ROOT / "src" / "litellm_lint" / "snapshots" / "litellm-1.108.4.json"


def load_script():
    spec = importlib.util.spec_from_file_location("gen_snapshot", ROOT / "scripts" / "gen_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_snapshot_shape_and_ast_scan(tmp_path):
    # --- built-in snapshot
    raw = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    assert SNAPSHOT_FILE.name == f"litellm-{raw['meta']['litellm_version']}.json"
    snap = load_snapshot("1.108.4")
    floors = {"router_settings": 45, "general_settings": 150, "litellm_settings": 400, "litellm_params": 200, "providers": 150}
    for section, floor in floors.items():
        assert len(snap[section]) >= floor, section
    assert "num_retries" in snap["router_settings"] and "default_fallbacks" in snap["router_settings"]
    assert "drop_params" in snap["litellm_settings"]
    assert "master_key" in snap["general_settings"] and "api_base" in snap["litellm_params"]
    assert "azure" in snap["providers"]
    assert all(isinstance(p, str) and not p.startswith("LlmProviders.") for p in snap["providers"])
    assert snap["meta"]["generator_version"] and snap["meta"]["sources"]
    assert "include" in snap["top_level"]  # top-level include directive (found via config_includes)
    assert "code_interpreter_interception_params" in snap["litellm_settings"]  # read in integrations/
    assert snap["rules"]["master_key"]["publicly_known_sha256"]

    # --- AST scan on fake source
    gen = load_script()
    source = '''
config.get("model_list")
x = config.get("router_settings", None)
general_settings.get("alerting")
general_settings["store_model_in_db"]
other.get("not_a_target")
if "key_management_system" in general_settings:
    pass
for key, value in litellm_settings.items():
    if key == "cache":
        pass
    elif key in ("callbacks", "success_callback"):
        pass
'''
    assert gen.scan_keys(source, ["config"]) == {"model_list", "router_settings"}
    assert gen.scan_keys(source, ["general_settings"]) == {"alerting", "store_model_in_db", "key_management_system"}
    assert gen.scan_keys(source, ["litellm_settings"]) == {"cache", "callbacks", "success_callback"}
    assert gen.scan_keys("def broken(:", ["config"]) == set()

    # --- enterprise paths are skipped
    (tmp_path / "proxy").mkdir()
    (tmp_path / "proxy" / "ok.py").write_text('general_settings.get("visible_key")\n')
    (tmp_path / "proxy" / "enterprise").mkdir()
    (tmp_path / "proxy" / "enterprise" / "paid.py").write_text('general_settings.get("hidden_key")\n')
    (tmp_path / "enterprise_billing").mkdir()
    (tmp_path / "enterprise_billing" / "x.py").write_text('general_settings.get("hidden_key2")\n')
    assert gen.scan_tree(tmp_path, ["general_settings"]) == {"visible_key"}
    assert gen.is_excluded_path("litellm/proxy/enterprise/x.py")
    assert not gen.is_excluded_path("litellm/proxy/proxy_server.py")

    # --- annotation simplifier
    assert gen.simplify_annotation(Optional[int])["type"] == ["integer", "null"]
    assert gen.simplify_annotation(Optional[list[str]])["type"] == ["array", "null"]
    assert gen.simplify_annotation(Literal["a", "b"]) == {"type": ["string"], "enum": ["a", "b"]}
    assert gen.simplify_annotation(Union[int, object])["type"] == ["any"]


@pytest.mark.skipif(
    os.environ.get("LITELLM_LINT_ALLOW_LITELLM") != "1",
    reason="needs litellm installed; run with LITELLM_LINT_ALLOW_LITELLM=1 (see README)",
)
def test_full_generation_matches_builtin_snapshot():
    pytest.importorskip("litellm")
    gen = load_script()
    snap = gen.build_snapshot()
    builtin = load_snapshot(snap["meta"]["litellm_version"])
    assert set(snap["router_settings"]) == set(builtin["router_settings"])
    assert set(snap["providers"]) == set(builtin["providers"])
