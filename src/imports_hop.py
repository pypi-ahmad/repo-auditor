"""Resolve one-hop local imports without leaving the selected root."""

import ast
from pathlib import Path


def _inside(root: Path, candidate: Path) -> Path | None:
    """Resolve a candidate only when it is an existing file inside ``root``.

    Args:
        root: Resolved boundary for the selected repository.
        candidate: Potential local import path.

    Returns:
        The resolved file path, or ``None`` when it is missing or escapes the root.
    """
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def _module_files(base: Path, module: str, root: Path) -> set[Path]:
    """Find a local module file or package initializer below the selected root.

    Args:
        base: Directory against which to resolve the dotted module name.
        module: Dotted import target.
        root: Selected repository boundary.

    Returns:
        Existing module files that remain contained by ``root``.
    """
    if not module:
        return set()
    parts = module.split(".")
    stem = base.joinpath(*parts)
    found = {
        path
        for candidate in (stem.with_suffix(".py"), stem / "__init__.py")
        if (path := _inside(root, candidate)) is not None
    }
    return found


def resolve_one_hop(file_path: Path, repo_root: Path) -> list[Path]:
    """Parse a Python file and return direct local imports under the selected root.

    Args:
        file_path: Python file already selected for the pack.
        repo_root: Root boundary that local imports must remain inside.

    Returns:
        Sorted, resolved local Python paths. Invalid, external, or unparsable imports are omitted.
    """
    root = repo_root.resolve()
    source = _inside(root, file_path)
    if source is None or source.suffix.lower() != ".py":
        return []

    try:
        tree = ast.parse(source.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, UnicodeError):
        return []

    found: set[Path] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for base in (source.parent, root):
                    found.update(_module_files(base, alias.name, root))
        elif isinstance(node, ast.ImportFrom):
            base = source.parent
            for _ in range(max(node.level - 1, 0)):
                base = base.parent

            module = node.module or ""
            bases = (base,) if node.level else (source.parent, root)
            for candidate_base in bases:
                found.update(_module_files(candidate_base, module, root))
                for alias in node.names:
                    child = f"{module}.{alias.name}" if module else alias.name
                    found.update(_module_files(candidate_base, child, root))

    found.discard(source)
    return sorted(found, key=lambda path: path.relative_to(root).as_posix())
