"""Pin the output language for the whole test run.

Importing this module sets ``LITELLM_LINT_LANG=en`` so that assertions written against the
English text pass whatever ``LANG`` the machine has. Test modules that exercise another
language pass ``--lang`` or monkeypatch the environment explicitly.
"""
from __future__ import annotations

import os

os.environ["LITELLM_LINT_LANG"] = "en"
os.environ.pop("LC_ALL", None)
os.environ.pop("LC_MESSAGES", None)
