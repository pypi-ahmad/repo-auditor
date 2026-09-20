"""Path safety and boundary enforcement for repo-auditor."""

from pathlib import Path


def validate_repo_path(raw_path: str) -> tuple[bool, str, Path | None]:
    """Validate user-entered repository path.

    Enforces:
    1. Non-empty string.
    2. Path exists and is a directory.
    3. Not a root drive (e.g. C:\\, D:\\, /).
    4. Parent traversal may only resolve back to the same starting directory.

    Args:
        raw_path: User-entered local directory path.

    Returns:
        A tuple of validity, a user-safe status message, and the resolved safe root when valid.
    """
    clean_str = raw_path.strip()
    if not clean_str:
        return False, "Repository path cannot be empty.", None

    try:
        resolved = Path(clean_str).resolve()
    except Exception as exc:
        return False, f"Invalid path syntax: {exc}", None

    normalized_parts = clean_str.replace("/", "\\").split("\\")
    if ".." in normalized_parts:
        first_parent = normalized_parts.index("..")
        starting_path = "\\".join(normalized_parts[:first_parent])
        try:
            starting_root = Path(starting_path).resolve()
        except Exception as exc:
            return False, f"Invalid traversal prefix: {exc}", None
        if resolved != starting_root:
            return False, "Parent-directory traversal escapes the selected root.", None

    if not resolved.exists():
        return False, f"Path does not exist: {resolved}", None

    if not resolved.is_dir():
        return False, f"Path is not a directory: {resolved}", None

    # Check for drive root or root directory
    # On Windows: Path("D:\\").anchor == "D:\\" and len(parts) == 1
    if resolved == Path(resolved.anchor) or len(resolved.parts) <= 1:
        return (
            False,
            f"Refusing to scan drive root ({resolved}). Provide a specific repository folder.",
            None,
        )

    mode = "Git repository" if (resolved / ".git").exists() else "folder"
    return True, f"Path is a valid {mode}.", resolved


def validate_relative_path(raw_path: str) -> tuple[bool, str]:
    """Reject absolute and parent-traversing file or glob inputs.

    Args:
        raw_path: Candidate path relative to a previously selected root.

    Returns:
        A validity flag and a user-safe explanation.
    """
    cleaned = raw_path.strip().replace("\\", "/")
    if not cleaned:
        return False, "Path cannot be empty."
    if Path(cleaned).is_absolute() or (len(cleaned) >= 2 and cleaned[1] == ":"):
        return False, "Absolute paths are not allowed; use a path relative to the selected root."
    if ".." in cleaned.split("/"):
        return False, "Parent-directory traversal ('..') is not allowed."
    return True, "Path is relative to the selected root."


def is_safe_child_path(root_path: Path, target_path: Path) -> bool:
    """Ensure a resolved target remains within a resolved root path.

    Args:
        root_path: Selected repository boundary.
        target_path: Candidate file or directory to inspect.

    Returns:
        ``True`` only when resolution keeps the target inside the root.
    """
    try:
        resolved_root = root_path.resolve()
        resolved_target = target_path.resolve()
        resolved_target.relative_to(resolved_root)
        return True
    except (ValueError, RuntimeError):
        return False
