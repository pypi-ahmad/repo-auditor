# Status

## Current state

- Windows-native Streamlit entry point: `app.py`
- Pages: Health, Select, Pack, Audit, Findings
- Sidebar defaults: `budget_chars=80000`, `max_files=40`
- Model label: `agnes-3.0-flash`
- Health checks only whether `AGNESAI_API_KEY` exists; it never displays the value.
- Agnes client uses the official OpenAI SDK with three retries for transient errors, including HTTP 429.
- Select requires a typed root or the explicit fixture button. It never starts a default drive scan.
- Git targets show separate base/head fields and use a read-only `git diff --name-only`; Git errors are displayed before a bounded folder fallback.
- `src/imports_hop.py` adds one-hop relative and same-folder Python imports without leaving the root.
- The manifest records path, bytes, inclusion status, and reason. Pack text is bounded by the character budget.
- Audit makes three separate Agnes calls over the same pack using `api_drift`, `secrets_patterns`, and `tests`.
- Findings use one validated schema and are deduplicated by `file + title`.
- Audit and Findings pages provide tables and JSON downloads.

## Local verification

The live audit smoke called Agnes three times using the cached mini fixture.

```powershell
.venv\Scripts\python scripts\smoke_pack.py
.venv\Scripts\python scripts\smoke_audit.py
.venv\Scripts\python scripts\smoke_sandbox.py
.venv\Scripts\python scripts\smoke_import.py
uv run ruff check app.py scripts src smoke_test.py smoke_test_prompt2.py
uv run python -m compileall -q app.py scripts src smoke_test.py smoke_test_prompt2.py
```

## Cache status

| Artifact | Current status |
| :--- | :--- |
| `data/cache/last_pack.json` | Exists; contains the four-file, 367-character `mini_pkg` pack |
| `data/cache/last_audit.json` | Exists; contains the latest three-pass `mini_pkg` audit |
| `b.py` calling missing `greetz` | Reported by the `api_drift` pass |

The audit smoke made exactly three calls, produced three deduplicated findings, and included the required `b.py` missing-`greetz` finding.

The sandbox smoke refuses `C:\` and `D:\`, accepts only the contained `mini_pkg\..\mini_pkg` round trip, verifies Git-error folder fallback, and writes `data/cache/sandbox_check.json`. The import smoke loads `app`, `src.pack`, and `src.audit` from `scripts/`.
