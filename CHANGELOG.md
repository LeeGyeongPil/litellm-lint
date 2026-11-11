# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.2] - 2026-11-11

### Fixed
- Text summary lines now use singular and plural correctly ("1 error", "1 warning", "0 errors", "2 warnings"), including the per-file lines and the `total:` line for several files. JSON output and exit codes are unchanged.

## [0.1.1] - 2026-11-11

### Fixed
- Text output now shows a problem found in an `include`d file with that file's own name (as the JSON output already did), instead of the main config's name plus the included file's line and column. This resolves the first 0.1.0 known limitation.

## [0.1.0] - 2026-11-11

### Added
- `litellm-lint check` with rules LL000-LL402 and LL900 (unknown keys, types, misplaced keys, fallback and alias reference integrity, `os.environ/` resolution, literal secrets, weak `master_key`, repeated deployments, unknown provider prefixes).
- `--env-file` (repeatable), `--no-os-env`, `--strict`, `--ignore`, `--format text|json`; exit codes 0 / 1 / 2.
- `litellm-lint schema`: JSON Schema (Draft 2020-12) export for editors.
- Built-in schema snapshot extracted from litellm 1.108.4 and `scripts/gen_snapshot.py` to regenerate it.
- Python API: `check_file`, `export_schema`, `Diagnostic`, `Report`, `Severity`, `LintUsageError`.
- `.pre-commit-hooks.yaml`, example configs, CI.

### Known limitations
- (Fixed in 0.1.1) In text mode, a problem found in an `include`d file is shown with the main config's file name plus the included file's line and column (JSON output has the right file).
- An `include` loop made of links, or a list used as a top-level mapping key, ends with "internal error" (exit 2) instead of an LL900 diagnostic.
- When anchors/aliases reuse the same `litellm_params` across many deployments, the same diagnostic is repeated once per deployment.
- (Fixed in 0.1.2) Summary lines were always plural ("1 errors", "1 warnings").
- `Report.diagnostics` from the Python API is not sorted by line; sort it yourself.

[Unreleased]: https://github.com/LeeGyeongPil/litellm-lint/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/LeeGyeongPil/litellm-lint/releases/tag/v0.1.2
[0.1.1]: https://github.com/LeeGyeongPil/litellm-lint/releases/tag/v0.1.1
[0.1.0]: https://github.com/LeeGyeongPil/litellm-lint/releases/tag/v0.1.0
