# Developer guide

## Purpose

Repo Auditor packs a bounded subset of a local repository, then can run three focused Agnes audit
passes on that pack. The packer is the product. A large context window does not make a whole
monorepo suitable for one prompt.

## Code map

| Area | Responsibility |
| :--- | :--- |
| `app.py` | Streamlit pages, session state, and presentation of pack/audit results. |
| `src/safety.py` | Typed-root validation and path-jail containment checks. |
| `src/pack.py` | File selection, read-only Git diff, budget enforcement, manifest, and pack cache. |
| `src/imports_hop.py` | One-hop local Python import resolution under the selected root. |
| `src/audit.py` | Three-pass prompts, finding normalization, deduplication, and audit cache. |
| `src/providers.py`, `src/agnes_client.py`, `src/config.py` | Agnes configuration and client creation. |
| `scripts/` | Pack, audit, sandbox, and import smoke entry points. |

## Runtime flow

1. The user types a local folder or Git repository path. Drive roots and escaping paths are refused.
2. For a Git target with both refs supplied, `pack_repository()` uses read-only
   `git diff --name-only base..head`; a Git failure is shown and falls back to a folder scan.
3. The packer keeps supported text files, adds direct local Python imports, records a manifest, and
   truncates pack text to the character budget.
4. `run_three_pass_audit()` sends that same pack text once to `api_drift`,
   `secrets_patterns`, and `tests`.
5. Caches are written only under this repository's ignored `data/cache/` directory.

## Public Python reference

### Packing

- `pack_repository(root_path, git_refs=None, budget_chars=80000, max_files=40)` returns
  `(ok, message, PackResult | None)` and never reads outside the resolved root.
- `save_pack_cache(result)` writes `data/cache/last_pack.json` unless a different cache path is
  explicitly passed.
- `PackResult` exposes packed files, manifest rows, one-hop links, text, and convenience totals.

### Safety and imports

- `validate_repo_path()` validates a selected root and returns a resolved `Path` only when safe.
- `is_safe_child_path()` is the final containment check before file reads.
- `resolve_one_hop()` returns direct local imports that resolve inside the selected root.

### Auditing

- `run_three_pass_audit()` requires the fixed Agnes provider/model and writes
  `data/cache/last_audit.json`.
- `parse_findings_json()` normalizes one model response to the shared finding contract.
- `AuditFinding` fields are `severity`, `file`, `title`, `evidence_span`, `pass_name`, and
  `recommendation`. Duplicate `file + title` records are removed.

## Cache contracts

`last_pack.json` stores the root, optional Git refs, budget, manifest, and bounded `pack_text`.
`last_audit.json` stores pack metadata, provider/model labels, pass summaries, and normalized
findings. Both are disposable local artifacts and must not be used as a source of credentials.

## Local validation

Run the commands in [the contributor runbook](CONTRIBUTOR_RUNBOOK.md). The normal offline set is
safe to run without an API key. The audit smoke is intentionally separate because it performs live
Agnes requests.
