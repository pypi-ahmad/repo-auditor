# Threat model

## Overview

Repo Auditor reads files from local repositories and sends code snippets to external LLM endpoints. This document outlines potential risks and the protections implemented in the code.

## Threat matrix

| ID | Description | Severity | Mitigation | Location |
| :--- | :--- | :--- | :--- | :--- |
| TM-01 | Path traversal or reading arbitrary files | High | Path canonicalization and boundary checks | `src/safety.py` |
| TM-02 | Scanning an entire drive root | Medium | Rejects drive roots (`D:\`, `C:\`, `/`) | `src/safety.py` |
| TM-03 | Modifying Git state through subprocess calls | High | Read-only GitPython calls; no shell commands | `src/pack.py` |
| TM-04 | Leaking API keys in logs or files | Critical | Keys stay in environment; presence check only | `src/providers.py` |
| TM-05 | Generating exploit payloads | High | Prompt requires location reporting only | `src/audit_llm.py` |
| TM-06 | Memory exhaustion from large files | Medium | 500 KB file limit and total character cap | `src/pack.py` |

## Defenses

### Read-only Git access

Repo Auditor never runs modifying Git commands such as `git reset`, `git clean`, `git checkout`, or `git push`. Git operations use GitPython read-only methods (`repo.git.diff`, `repo.git.ls_files`, and `repo.untracked_files`). Staging areas, branch heads, and commit history remain unchanged.

### Path containment

Drive roots such as `C:\`, `D:\`, or `/` are rejected during path validation to prevent accidental scanning of system directories.

Every candidate file is verified with `is_safe_child_path` before reading:

```python
def is_safe_child_path(root_path: Path, target_path: Path) -> bool:
    try:
        resolved_root = root_path.resolve()
        resolved_target = target_path.resolve()
        resolved_target.relative_to(resolved_root)
        return True
    except (ValueError, RuntimeError):
        return False
```

Symlinks are resolved before checking whether the path sits inside the repository root. Any link pointing outside the root is skipped.

### Environment variables and credentials

API keys (`AGNESAI_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`) stay in process memory and are never written to disk or logs. The application checks only whether an environment variable exists to toggle provider options in the interface.

The `.env.example` file contains variable names with empty values, and `.gitignore` excludes `.env` and `.streamlit/secrets.toml`. In static audit mode, patterns matching credential formats are replaced with `[REDACTED]` before display.

### Exploit prevention

When Pass 2 checks code for security vulnerabilities, its prompt explicitly instructs the model:

> Report locations only. DO NOT write exploits, attack payloads, or weaponized instructions.

The output provides file locations, line references, and remediation advice rather than attack examples.

### Resource limits

Files larger than 500 KB are skipped during packing. Total characters are bounded by a configurable cap (default 120,000 characters) to prevent runaway memory usage and stay well within model context limits. Binary files and files containing null bytes in their opening bytes are skipped automatically.
