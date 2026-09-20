# Contributor onboarding

## Goal

Use a fresh Windows checkout to build and verify an offline pack of `mini_pkg`, without calling
Agnes.

## Prerequisites

- Windows 11 and the Windows `py` launcher for Python 3.
- Git, if you intend to inspect Git-diff behavior.
- An optional User environment variable `AGNESAI_API_KEY` for the live audit only.

## Set up and launch

From the repository root, run:

```cmd
run.cmd
```

On the first run, `run.cmd` copies `.env.example` to `.env`, opens it in Notepad, and exits. Do not
put a real key in version control. Start the script again to create `.venv`, install
`requirements.txt`, and launch Streamlit.

The Health page reports only whether `AGNESAI_API_KEY` is available to the current process. If a
key was added after the terminal or editor opened, restart that host.

## First offline checkpoint

1. Select **Load fixture** in the app or enter `data/fixtures/mini_pkg` as the path.
2. Gather and pack it. The result should include `a.py`, `b.py`, `c.py`, and `README.md`.
3. Confirm the manifest explains each inclusion and the pack contains `def greet` and `greetz`.

The command-line equivalent is:

```powershell
.venv\Scripts\python scripts\smoke_pack.py
```

It writes `data/cache/last_pack.json` and does not call Agnes.

## Next steps

- Read the [developer guide](DEVELOPER_GUIDE.md) before changing a module.
- Use the [contributor runbook](CONTRIBUTOR_RUNBOOK.md) when a check fails.
- Follow the [zero-to-mastery tutorial](ZERO_TO_MASTERY.md) for the full product flow.
