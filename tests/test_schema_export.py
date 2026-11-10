"""AC-9: exported JSON Schema."""
from __future__ import annotations

import json

import pytest

jsonschema = pytest.importorskip("jsonschema")

from litellm_lint import export_schema  # noqa: E402
from litellm_lint.cli import main  # noqa: E402
from litellm_lint.loader import load_config, to_plain  # noqa: E402

from conftest import EXAMPLES  # noqa: E402


def test_exported_schema_valid_and_catches_types(tmp_path):
    out = tmp_path / "litellm.schema.json"
    assert main(["schema", "-o", str(out)]) == 0
    schema = json.loads(out.read_text(encoding="utf-8"))
    assert schema == json.loads(json.dumps(export_schema()))

    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "1.108.4" in schema["$id"] and "1.108.4" in schema["title"]

    validator = jsonschema.Draft202012Validator(schema)
    good = to_plain(load_config(EXAMPLES / "good_config.yaml"))
    assert list(validator.iter_errors(good)) == []

    def errors_for(section, key, value):
        doc = json.loads(json.dumps(good))
        doc[section][key] = value
        return [e.message for e in validator.iter_errors(doc)]

    assert errors_for("router_settings", "default_fallbacks", "x")
    assert errors_for("router_settings", "num_retries", "three")
    assert errors_for("litellm_settings", "fallbacks", "x")
    # allowed spellings
    assert errors_for("router_settings", "num_retries", 5) == []
    assert errors_for("router_settings", "num_retries", "os.environ/RETRIES") == []
    # typos in router_settings are rejected, litellm_settings stays open
    assert errors_for("router_settings", "num_retires", 3)
    assert errors_for("litellm_settings", "my_custom_flag", 1) == []


def test_schema_to_stdout(capsys):
    assert main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["title"].startswith("LiteLLM proxy config.yaml")
