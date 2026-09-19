# Repo Auditor

> "512K is not 'whole monorepo': the packer is the product."

Repo Auditor is a Streamlit app on Windows 11 for auditing code changes with Agnes AI (`agnes-3.0-flash`).

## Why the packer is the product

Large context windows still cannot hold an entire repository. Even when a codebase fits, sending hundreds of files increases latency, token costs, and missed details. Reviewing changed files together with their immediate dependencies keeps the model focused on real changes.

The packer prepares context through four steps:

- Git diff inspection: targets changed files against `origin/HEAD`, a user-specified ref, or working tree diffs using read-only Git operations (no commits, pushes, or resets).
- AST import expansion: parses Python ASTs in changed files to find local imports and include their definitions.
- Character cap: stops packing once total characters reach the chosen limit (default 120,000 characters, with 500 KB per-file ceiling).
- Manifest: lists each file path, size, inclusion status, and reason for inclusion or exclusion.

For non-git folders, the app supports explicit file lists or glob patterns such as `src/**/*.py` with a file count limit.

## Audit passes

The auditor runs three separate passes instead of one prompt:

| Pass | Focus | Output schema |
| :--- | :--- | :--- |
| Pass 1: Breaking API and call-site drift | Renamed, removed, or signature-modified functions where callers use old APIs | `{severity, file, title, evidence_span, recommendation}` |
| Pass 2: Security and credentials | Injection risks and hardcoded secrets. Reports locations only; no exploit code generated | `{severity, file, title, evidence_span, recommendation}` |
| Pass 3: Test coverage | Public functions and classes in changed code that lack test coverage | `{severity, file, title, evidence_span, recommendation}` |

Findings are saved to `data/cache/last_audit.json` and pack metadata to `data/cache/last_pack.json`.

## Quick start (Windows 11)

### Prerequisites

- Windows 11
- Python 3.11 or newer (or `uv`)
- Environment variable `AGNESAI_API_KEY` set

### Launch with run.cmd

Double-click `run.cmd` in the repository root or run it in a terminal:

```cmd
run.cmd
```

The script checks for `.env`, copies `.env.example` if needed, builds `.venv` with `py -3`, installs `requirements.txt`, and starts Streamlit.

To run with `uv`:

```powershell
uv sync
uv run streamlit run app.py
```

## Environment variables

Repo Auditor reads environment variables from the current process without printing their values:

| Variable | Scope | Description |
| :--- | :--- | :--- |
| `AGNESAI_API_KEY` | Required | Key for default provider Agnes AI (`https://apihub.agnes-ai.com/v1`). |
| `OPENAI_API_KEY` | Optional | Key for OpenAI gateway. Hidden when unset. |
| `OPENAI_BASE_URL` | Optional | Custom base URL for OpenAI provider. |
| `GOOGLE_API_KEY` | Optional | Key for Google Gemini provider. Hidden when unset. |

## Testing and fixtures

The repository includes a test fixture in `data/fixtures/mini_pkg`:
- `a.py` defines `greet(name)` (renamed from `say_hello`).
- `b.py` imports `greet as greetz`, but also calls `say_hello`, which was renamed and no longer exists in `a.py`.
- `README.md` documents fixture usage.

Run the test suite to verify AST packaging, break detection, and cache generation:

```powershell
uv run python smoke_test_prompt2.py
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system structure, pipeline stages, and module relationships.
- [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md): read-only Git policy, path containment, and security boundaries.
- [STATUS.md](STATUS.md): test log and component verification status.
