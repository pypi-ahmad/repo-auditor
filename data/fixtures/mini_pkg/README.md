# Mini Package Fixture

Test fixture demonstrating breaking API changes and call-site drift.

## Modules

- `a.py`: defines `greet(name)` (renamed from `say_hello`).
- `b.py`: imports `greet as greetz`, but also attempts to import and call `say_hello`, which was renamed and no longer exists in `a.py`.

## Purpose

Used by Repo Auditor smoke tests to verify:
1. AST one-hop dependency resolution (`b.py` -> `a.py`).
2. Manifest generation with inclusion reasons.
3. Agnes AI detection of the missing/renamed function call.
