"""Built-in schema snapshot (keys extracted from a specific litellm version)."""
from __future__ import annotations

import importlib.metadata as importlib_metadata
import json
from functools import lru_cache
from importlib import resources
from typing import Any

DEFAULT_LITELLM_VERSION = "1.108.4"


@lru_cache(maxsize=4)
def load_snapshot(litellm_version: str = DEFAULT_LITELLM_VERSION) -> dict[str, Any]:
    """Load ``snapshots/litellm-<version>.json`` shipped inside the package."""
    name = f"litellm-{litellm_version}.json"
    try:
        text = resources.files("litellm_lint").joinpath("snapshots", name).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise FileNotFoundError(
            f"no schema snapshot for litellm {litellm_version} (looked for snapshots/{name}). "
            "Generate one with scripts/gen_snapshot.py inside an environment that has that litellm installed."
        ) from exc
    data = json.loads(text)
    if data["meta"]["litellm_version"] != litellm_version:
        raise ValueError(f"{name}: meta.litellm_version is {data['meta']['litellm_version']!r}, file name says otherwise")
    return data


def installed_litellm_version() -> str | None:
    """Installed litellm version from package metadata, or None. Never imports litellm."""
    try:
        return importlib_metadata.version("litellm")
    except importlib_metadata.PackageNotFoundError:
        return None
