# Threat model

## Overview

Repo Auditor reads local repository files and sends code snippets to an external LLM endpoint. This document describes the risks and the protections in the code.

## Threat matrix

| ID | Description | Severity | Mitigation | Location |
| :--- | :--- | :--- | :--- | :--- |
| TM-01 | Path traversal or reading arbitrary files | High | Path canonicalization and boundary checks | `src/safety.py` |
| TM-02 | Scanning an entire drive root | Medium | Rejects drive roots (`D:\`, `C:\`, `/`) | `src/safety.py` |
| TM-03 | Modifying Git state | High | GitPython is limited to commit resolution and read-only `git diff --name-only` | `src/pack.py` |
| TM-04 | Leaking API keys in logs or files | Critical | `AGNESAI_API_KEY` stays in the process; presence check only | `src/providers.py` |
| TM-05 | Generating exploit payloads | High | Prompt and post-processing limit security findings to categorical titles and locations | `src/audit.py` |
| TM-07 | Prompt injection in repository content | High | Repository text is marked untrusted and cannot override pass instructions | `src/audit.py` |
| TM-06 | Oversized model input | Medium | File-count and total-character caps | `src/pack.py` |

## Defenses

### Read-only Git access

Repo Auditor never runs modifying Git commands such as `git reset`, `git clean`, `git checkout`, or `git push`. The packer resolves the supplied commits, then uses GitPython's read-only `git diff --name-only base..head`. Staging areas, branch heads, the working tree, and commit history remain unchanged.

### Path jail

Drive roots such as `C:\`, `D:\`, or `/` are rejected during path validation to prevent accidental scanning of system directories.

A path containing `..` is accepted only when canonical resolution returns to the same pre-traversal directory, such as `mini_pkg\..\mini_pkg`. Any traversal resolving elsewhere is refused.

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

Symlinks are resolved before checking whether the path sits inside the repository root. Any link pointing outside the root is skipped. The typed repository is a read-only source; Repo Auditor writes cache data only beneath its own `data/cache/` directory.

### Environment variables and credentials

`AGNESAI_API_KEY` stays in process memory and is never written to disk or logs. The application checks only whether the environment variable exists.

The `.env.example` file contains variable names with empty values, and `.gitignore` excludes `.env` and `.streamlit/secrets.toml`. In static audit mode, patterns matching credential formats are replaced with `[REDACTED]` before display.

### Exploit prevention

When Pass 2 checks code for security vulnerabilities, its prompt explicitly instructs the model:

> Report locations only. DO NOT write exploits, attack payloads, or weaponized instructions.

The security output is reduced to a file path, categorical title, and location-only evidence. Its recommendation is forced to an empty string. It cannot retain source snippets, secrets, remediation text, exploits, or password-guessing recipes.

The security pass reports locations only and does not develop exploits.

### Resource limits

File count and total characters are bounded by configurable caps (defaults: 40 files and 80,000 characters). Binary files and files containing null bytes in their opening bytes are skipped automatically.
