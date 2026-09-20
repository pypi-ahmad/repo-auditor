# Contributor runbook

## Standard offline verification

Run these from the repository root after changing code or documentation examples:

```powershell
uv run ruff check app.py scripts src smoke_test.py smoke_test_prompt2.py
uv run python -m compileall -q app.py scripts src smoke_test.py smoke_test_prompt2.py
.venv\Scripts\python scripts\smoke_pack.py
.venv\Scripts\python scripts\smoke_sandbox.py
.venv\Scripts\python scripts\smoke_import.py
uv run python smoke_test.py
```

The pack, sandbox, import, and regression smokes are offline. `smoke_sandbox.py` writes
`data/cache/sandbox_check.json`; the cache directory is ignored by Git.

## Intentional live audit validation

Only run this when `AGNESAI_API_KEY` is available and you intend to make three external calls:

```powershell
.venv\Scripts\python scripts\smoke_audit.py
```

Run `smoke_pack.py` first. The audit smoke requires its `mini_pkg` cache and verifies that the
`api_drift` result identifies `b.py` calling missing `greetz`.

## Failure handling

| Symptom | Check | Action |
| :--- | :--- | :--- |
| Drive root or path is refused | The path must not be `C:\` or `D:\`. | Use a specific local directory; do not weaken the path jail. |
| Git diff fails | Base and head must both be present and resolve. | Read the displayed error; the app safely falls back to a folder scan. |
| No files are packed | Check supported extensions, budget, and max-files settings. | Use the manifest reasons; do not bypass containment checks. |
| Agnes key appears missing | The process may predate the User environment change. | Restart the terminal/editor; never print or paste the key. |
| Audit smoke rejects the cache | `last_pack.json` must come from `mini_pkg`. | Rerun `scripts\smoke_pack.py`, then rerun the audit smoke. |

## Safety reminders

Audited repositories are read-only targets. Do not add modifying Git commands, external writes to a
typed root, exploit payloads, password-guessing recipes, or security source snippets to the app or
documentation.
