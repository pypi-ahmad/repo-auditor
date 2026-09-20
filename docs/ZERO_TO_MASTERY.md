# Zero to mastery: Repo Auditor

## What you will learn

This tutorial covers bounded packs, one-hop import expansion, and how to interpret the three audit
passes. Repo Auditor does not present a whole monorepo as one model context.

## 1. Start with the fixture

Run the offline pack smoke:

```powershell
.venv\Scripts\python scripts\smoke_pack.py
```

It packs `data/fixtures/mini_pkg`. The fixture deliberately contains two API-drift problems:

- `b.py` imports `greet` but calls `greetz("Ada")`.
- `c.py` imports `unused_name` from `b.py`, where it is not exported.

Open `data/cache/last_pack.json`. The pack contains headers around each file and a manifest row
that explains why it was included. This bounded context is what the audit receives.

## 2. Understand containment and selection

Run the sandbox smoke:

```powershell
.venv\Scripts\python scripts\smoke_sandbox.py
```

It proves that drive roots are refused, a canonical `mini_pkg\..\mini_pkg` round trip stays inside
the fixture, and an invalid Git ref falls back to a folder scan. The target is never modified.

## 3. Use the Streamlit workflow

1. Launch `run.cmd`.
2. On **Select**, type a specific local folder or choose **Load fixture**.
3. For a Git repository, optionally supply both base and head refs for a read-only diff.
4. On **Pack**, inspect the manifest, character budget, and one-hop import graph.
5. On **Audit**, review the three pass descriptions before choosing to run the model.

## 4. Optional: run the live audit

This step sends the fixture pack to Agnes three times. It is optional and requires
`AGNESAI_API_KEY` in the current Windows process.

```powershell
.venv\Scripts\python scripts\smoke_audit.py
```

The smoke writes `data/cache/last_audit.json` and requires an `api_drift` finding for `b.py` and
`greetz`. The security pass reports locations and categorical patterns only. It does not generate
exploit payloads or reproduce secrets.

## 5. Read findings critically

The model output is a starting point, not proof. Confirm a finding against the packed source and the
manifest. `api_drift` examines calls/imports, `secrets_patterns` reports only locations for key-like
assignments or `shell=True`, and `tests` identifies public or changed code without visible tests.

## Where to go next

- [Developer guide](DEVELOPER_GUIDE.md) for module and API detail.
- [Contributor runbook](CONTRIBUTOR_RUNBOOK.md) for repeatable verification.
- [Threat model](THREAT_MODEL.md) for containment and security limits.
