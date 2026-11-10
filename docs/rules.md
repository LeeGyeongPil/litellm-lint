# Rules

Every finding has a stable code. Severity is `error`, `warning` or `info`.
`check` exits 1 when there is an error (or a warning with `--strict`), 2 for usage or YAML errors.
Skip codes with `--ignore LL001,LL402`. Messages never contain config or `.env` values, only key paths and names.

| Code | Default | Meaning |
|---|---|---|
| LL000 | info | Installed `litellm` version differs from the schema snapshot (read from package metadata; litellm is never imported). |
| LL001 | error / warning / info | Unknown key. A close key in the same section, or the key exists in another section: error with a suggestion. Nothing close: warning (may be newer than the snapshot). In `model_list[].litellm_params` (the proxy passes extra keys to the provider): warning with a suggestion, otherwise info. |
| LL002 | error | Wrong type or shape (`num_retries: three`, `default_fallbacks: "gpt-main"`, a section that is not a mapping, a fallback list element that is not `{source: [target, ...]}`, an `include` that is not a list of paths, a non-text top-level key, a `model_list` entry without `model_name` / `litellm_params` / `model`). `os.environ/NAME`, numeric text and empty values are accepted. |
| LL003 | error | `router_settings.health_check_interval` / `health_check_concurrency`: the proxy refuses to start; move them to `general_settings`. |
| LL101 | error | A `fallbacks`, `context_window_fallbacks`, `content_policy_fallbacks` or `default_fallbacks` target is not a `model_name` (wildcards and aliases count). Warning if `store_model_in_db: true` or `model_list` is empty. |
| LL102 | warning | A fallback source group is not a `model_name` (`"*"` is allowed). |
| LL103 | error | A `model_group_alias` points at a group that is not a `model_name` (both `name: group` and `name: {model, hidden}` forms). |
| LL104 | warning | A `model_group_retry_policy` group is not a `model_name`. |
| LL201 | error | `os.environ/NAME` is not defined in any `--env-file`, the config's `environment_variables`, or the process environment. Info when `general_settings.key_management_system` is set. Only the name is shown. |
| LL202 | warning | A literal value under a key like `api_key`, `*_password`, `*_secret`, `*_token`. The value is never printed. |
| LL301 | error | `general_settings.master_key` is empty or a publicly known example key: the proxy refuses to start (litellm 1.108.4 `master_key_boot_check.py`). Warning if `dangerously_permit_weak_or_unset_master_key` is true. |
| LL401 | warning | A deployment repeats an earlier one exactly (same `model_name` and `litellm_params`). The same name with different params is load balancing and is not reported. |
| LL402 | warning / info | Provider prefix in `litellm_params.model` is not a litellm provider. Warning with a suggestion; info without. Skipped when `custom_llm_provider` is set. |
| LL900 | error (exit 2) | YAML could not be parsed, or the input is refused: nesting deeper than 100 levels, more than 500,000 nodes after alias expansion (alias bomb), an `include` file that is missing, unreadable, not a mapping or part of a chain longer than 50 files. Reported as `line:col` plus a generic description; source lines are never echoed. |

## Reference resolution

A *model group* is all `model_list` entries sharing one `model_name`. Repeating a name is load balancing.
A name resolves if it equals a `model_name`, matches a wildcard `model_name` such as `openai/*` (fnmatch), or is a `model_group_alias` key.
Fallbacks are read from both `litellm_settings` and `router_settings`.
