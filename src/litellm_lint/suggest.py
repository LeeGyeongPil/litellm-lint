"""'Did you mean' helper."""
from __future__ import annotations

import difflib
from typing import Iterable


def closest(name: str, candidates: Iterable[str], cutoff: float = 0.8) -> str | None:
    """Best close match for ``name`` or None. Exact matches are not suggestions."""
    pool = [c for c in candidates if c != name]
    match = difflib.get_close_matches(name, pool, n=1, cutoff=cutoff)
    return match[0] if match else None
