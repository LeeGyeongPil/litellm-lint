"""``check_file``: load, run the rules, collect a Report."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from . import snapshot as snapshot_mod
from .context import Context
from .diagnostics import Diagnostic, Report, Severity, apply_ignore, validate_codes
from .includes import collect_included_models
from .loader import YamlProblem, load_config
from .rules import deployments, env, keys, refs, safety


def check_file(
    path: str | Path,
    env_files: Iterable[str | Path] = (),
    use_os_env: bool = True,
    ignore: Iterable[str] = (),
) -> Report:
    """Statically check one LiteLLM proxy config file.

    ``env_files`` are dotenv files whose variable *names* count as defined. With
    ``use_os_env`` the current process environment counts too. ``ignore`` drops rule codes.
    Raises ``LintUsageError`` for unusable inputs; YAML syntax problems become an LL900
    diagnostic in the returned report.
    """
    ignore = list(ignore)
    validate_codes(ignore)
    cfg_path = Path(path)
    snap = snapshot_mod.load_snapshot()
    report = Report(
        str(cfg_path),
        snapshot_version=snap["meta"]["litellm_version"],
        snapshot_generated_at=snap["meta"]["generated_at"],
    )
    sources = env.build_sources([Path(p) for p in env_files], use_os_env)
    try:
        config = load_config(cfg_path)
        included = collect_included_models(config, cfg_path)
    except YamlProblem as problem:
        report.diagnostics = apply_ignore([problem.diagnostic], ignore)
        return report

    ctx = Context(str(cfg_path), config, snap, sources, included)
    found: list[Diagnostic] = []
    installed = snapshot_mod.installed_litellm_version()
    if installed and installed != snap["meta"]["litellm_version"]:
        found.append(
            ctx.diag(
                "LL000",
                Severity.INFO,
                f"installed litellm {installed} differs from schema snapshot {snap['meta']['litellm_version']}; "
                "keys added in newer releases may be reported as unknown",
            )
        )
    try:
        for module in (keys, refs, env, safety, deployments):
            found.extend(module.check(ctx))
    except RecursionError:  # the loader limits depth, so this is only a last line of defence
        report.diagnostics = apply_ignore(
            [ctx.diag("LL900", Severity.ERROR, "nesting too deep: the document could not be walked", (1, 1))], ignore
        )
        return report
    report.diagnostics = apply_ignore(found, ignore)
    return report
