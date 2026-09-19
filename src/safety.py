"""Path safety and boundary enforcement for repo-auditor."""

from pathlib import Path
from typing import Tuple


def validate_repo_path(raw_path: str) -> Tuple[bool, str, Path | None]:
    """Validate user-entered repository path.

    Enforces:
    1. Non-empty string.
    2. Path exists and is a directory.
    3. Not a root drive (e.g. C:\\, D:\\, /).
    4. Is a valid git repository or contains .git directory.

    Returns:
        (is_valid, error_or_success_message, resolved_path)
    """
    clean_str = raw_path.strip()
    if not clean_str:
        return False, "Repository path cannot be empty.", None

    try:
        resolved = Path(clean_str).resolve()
    except Exception as exc:
        return False, f"Invalid path syntax: {exc}", None

    if not resolved.exists():
        return False, f"Path does not exist: {resolved}", None

    if not resolved.is_dir():
        return False, f"Path is not a directory: {resolved}", None

    # Check for drive root or root directory
    # On Windows: Path("D:\\").anchor == "D:\\" and len(parts) == 1
    if resolved == Path(resolved.anchor) or len(resolved.parts) <= 1:
        return False, f"Refusing to scan drive root ({resolved}). Provide a specific repository folder.", None

    # Git repository check
    git_dir = resolved / ".git"
    if not git_dir.exists():
        return False, f"Directory is not a git repository (missing .git): {resolved}", None

    return True, "Path is valid.", resolved


def is_safe_child_path(root_path: Path, target_path: Path) -> bool:
    """Ensure target_path resolves strictly within root_path, preventing path traversal."""
    try:
        resolved_root = root_path.resolve()
        resolved_target = target_path.resolve()
        resolved_target.relative_to(resolved_root)
        return True
    except (ValueError, RuntimeError):
        return False
