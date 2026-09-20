# Repo Auditor

> 512K is not the whole monorepo. The packer is the product.

Repo Auditor is a Windows 11 Streamlit app that audits a bounded set of code files with Agnes AI (`agnes-3.0-flash`). It selects files, follows one local Python import hop, and enforces a character budget before sending a pack to the model.

## Why the packer is the product

Large context windows still leave a file-selection problem. Sending hundreds of files raises latency and token costs, and it can bury the details that matter. The packer pairs changed files with their immediate dependencies so the model can review the relevant code.

The packer prepares context through four steps:

- File selection: Git targets offer separate base/head fields and use a read-only `git diff --name-only base..head`; if Git fails, the error is shown and the bounded folder scan is used. Other targets scan `.py`, `.md`, `.txt`, and `.toml` files.
- AST import expansion: parses packed Python files and adds one-hop relative or same-folder imports within the typed root.
- Character cap: truncates the concatenated pack at the chosen limit (default 80,000 characters).
- Manifest: lists each file path, size, inclusion status, and reason for inclusion or exclusion.

The selected root is required. The packer skips `.git`, `.venv`, `node_modules`, binary files, and any path that escapes the root.

## Audit passes

The auditor runs three separate passes instead of one prompt:

| Pass | Focus | Output schema |
| :--- | :--- | :--- |
| `api_drift` | Broken imports, renamed callees, and missing symbols | Shared finding schema |
| `secrets_patterns` | Hardcoded key-like assignments and `subprocess(..., shell=True)` locations only | Shared finding schema with empty recommendation |
| `tests` | Changed or public functions without visible tests | Shared finding schema |

Every finding uses `{severity, file, title, evidence_span, pass_name, recommendation}`. Severities are `high`, `medium`, `low`, or `info`; identical `file + title` findings are deduplicated.

Findings are saved to `data/cache/last_audit.json` and pack metadata to `data/cache/last_pack.json`.

## Quick start (Windows 11)

### Prerequisites

- Windows 11
- Python 3.11 or newer through the Windows `py` launcher
- Windows User environment variable `AGNESAI_API_KEY`

### Launch with run.cmd

Double-click `run.cmd` in the repository root or run it in a terminal:

```cmd
run.cmd
```

If `.env` is absent, the script copies `.env.example`, opens it in Notepad, and exits. On the next run it builds `.venv` with `py -3`, installs `requirements.txt`, and starts Streamlit.

To run with `uv`:

```powershell
uv sync
uv run streamlit run app.py --server.port 8594
```

`run.cmd` starts Repo Auditor at `http://localhost:8594`. Before launching, it stops any existing
process that is listening on port 8594.

## Environment variables

Repo Auditor reads `AGNESAI_API_KEY` from the current Windows process with `os.environ`. The fixed Agnes endpoint is `https://apihub.agnes-ai.com/v1`. The app never prints, logs, or writes the value. If you added the key after starting a terminal or editor, restart that program.

`.env.example` contains names only. Repo Auditor does not load credentials from `.env`.

## v1 boundaries

No WSL2, Docker, OCR, Qdrant, or PDF processing. There is no GitHub Actions workflow in v1. Git access is read-only. Cache files are written only under this app's ignored `data/cache/` directory; the selected target is never modified.

## Testing and fixtures

The repository includes a test fixture in `data/fixtures/mini_pkg`:

- `a.py` defines `greet(name)`.
- `b.py` imports `greet` and intentionally calls undefined `greetz("Ada")`.
- `c.py` intentionally imports missing `unused_name` from `b.py`.
- `README.md` documents fixture usage.

From the repository root, run the pack smoke to package `mini_pkg`, verify one-hop selection, and write `data/cache/last_pack.json` without calling Agnes:

```powershell
.venv\Scripts\python scripts\smoke_pack.py
```

Then run the optional live audit smoke to load that exact fixture cache, call Agnes three times,
and write `data/cache/last_audit.json`. It requires `AGNESAI_API_KEY`:

```powershell
.venv\Scripts\python scripts\smoke_audit.py
```

Sandbox and import checks:

```powershell
.venv\Scripts\python scripts\smoke_sandbox.py
.venv\Scripts\python scripts\smoke_import.py
```

## Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md): contributor boundaries and guide entry point.
- [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md): module map, public APIs, and caches.
- [docs/ONBOARDING.md](docs/ONBOARDING.md): Windows setup and first offline checkpoint.
- [docs/CONTRIBUTOR_RUNBOOK.md](docs/CONTRIBUTOR_RUNBOOK.md): verification and failure handling.
- [docs/ZERO_TO_MASTERY.md](docs/ZERO_TO_MASTERY.md): guided packer-to-findings tutorial.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system structure, pipeline stages, and module relationships.
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md): read-only Git policy, path containment, and security boundaries.
- [STATUS.md](STATUS.md): test log and component verification status.
