# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-12

### Added
- Output language selection, English or Korean, for the whole CLI: `--help`, argparse errors, the text report (diagnostic messages, severity words, summary lines with singular/plural), usage errors and progress lines. Choose it with `--lang en|ko` (accepted before or after the subcommand), the `LITELLM_LINT_LANG` environment variable, or the locale (`LC_ALL`, `LC_MESSAGES`, `LANG`; a value starting with `ko` means Korean). Anything else, or an invalid value, means English. Every message lives in one table, `litellm_lint/i18n.py`, and a test checks that both languages have the same keys and placeholders.

### Changed
- The default language now follows the environment: with a Korean locale the text output and `--help` are in Korean. Scripts that parse the text output should pass `--lang en` (or set `LITELLM_LINT_LANG=en`), or switch to `--format json`.
- Text report: nothing else changes in English. `Diagnostic.message` stays English for library users.

### Unchanged
- `--format json` output (keys, structure, values including `message`), the `schema` command's JSON Schema, rule IDs and exit codes are identical in both languages.

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

[Unreleased]: https://github.com/LeeGyeongPil/litellm-lint/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/LeeGyeongPil/litellm-lint/releases/tag/v0.2.0
[0.1.2]: https://github.com/LeeGyeongPil/litellm-lint/releases/tag/v0.1.2
[0.1.1]: https://github.com/LeeGyeongPil/litellm-lint/releases/tag/v0.1.1
[0.1.0]: https://github.com/LeeGyeongPil/litellm-lint/releases/tag/v0.1.0
