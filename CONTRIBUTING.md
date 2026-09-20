# Contributing to Repo Auditor

Repo Auditor is a Windows-native Streamlit application. Contributions must keep the pack bounded
and avoid implying that a whole monorepo fits in one model context.

## Start here

1. Read the [developer guide](docs/DEVELOPER_GUIDE.md) for the module map and public APIs.
2. Follow [onboarding](docs/ONBOARDING.md) to set up the Windows environment and run the
   offline fixture smoke.
3. Use the [contributor runbook](docs/CONTRIBUTOR_RUNBOOK.md) for verification and failures.
4. Work through the [zero-to-mastery tutorial](docs/ZERO_TO_MASTERY.md) to understand the
   packer and optional live audit.

## Contribution boundaries

- Keep all work in this repository. A path typed into the app is a read-only audit target.
- Do not add WSL2, Docker, GitHub Actions, OCR, Qdrant, PDF processing, or a documentation site
  in v1.
- Never expose, log, commit, or copy `AGNESAI_API_KEY`. The application reads it from the current
  Windows process only.
- Git access to an audited target is read-only. Do not introduce commit, push, reset, clean, or
  checkout operations.

## Before handing off a change

Run the offline checks in the runbook. The live audit smoke is optional and makes three external
Agnes calls, so run it only when intentionally validating that integration.
