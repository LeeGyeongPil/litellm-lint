"""LL401 repeated identical deployments, LL402 unknown provider prefixes."""
from __future__ import annotations

import json

from ..context import Context
from ..diagnostics import Diagnostic, Severity
from ..loader import item_pos, to_plain, value_pos
from ..suggest import closest


def check(ctx: Context) -> list[Diagnostic]:
    out: list[Diagnostic] = []
    models = ctx.config.get("model_list")
    if not isinstance(models, list):
        return out
    providers = set(ctx.snapshot["providers"])
    first_seen: dict[str, int] = {}
    for i, entry in enumerate(models):
        if not isinstance(entry, dict) or not isinstance(entry.get("litellm_params"), dict):
            continue
        params = entry["litellm_params"]
        name = entry.get("model_name")
        # Same name with *different* params is load balancing and is not reported.
        fingerprint = json.dumps([to_plain(name), to_plain(params)], sort_keys=True, default=str)
        if fingerprint in first_seen:
            out.append(
                ctx.diag(
                    "LL401",
                    Severity.WARNING,
                    f"model_list[{i}] repeats model_list[{first_seen[fingerprint]}] exactly (same model_name and litellm_params); "
                    "it only doubles that deployment's share of traffic",
                    item_pos(models, i),
                    None,
                    f"model_list[{i}]",
                )
            )
        else:
            first_seen[fingerprint] = i

        model = params.get("model")
        if (
            isinstance(model, str)
            and "/" in model
            and not model.startswith("os.environ/")
            and "custom_llm_provider" not in params
        ):
            prefix = model.split("/", 1)[0]
            if prefix not in providers:
                hint = closest(prefix, providers, cutoff=0.75)
                path = f"model_list[{i}].litellm_params.model"
                if hint:
                    out.append(
                        ctx.diag(
                            "LL402",
                            Severity.WARNING,
                            f"provider prefix '{prefix}' in {path} is not a litellm provider (did you mean '{hint}'?)",
                            value_pos(params, "model"),
                            hint,
                            path,
                        )
                    )
                else:
                    out.append(
                        ctx.diag(
                            "LL402",
                            Severity.INFO,
                            f"provider prefix '{prefix}' in {path} is not in the litellm provider list; "
                            "fine if custom_llm_provider is set elsewhere",
                            value_pos(params, "model"),
                            None,
                            path,
                        )
                    )
    return out
