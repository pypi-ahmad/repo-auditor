"""Python AST-based local import resolver for one-hop dependency discovery."""

import ast
from pathlib import Path

from src.safety import is_safe_child_path


def get_local_imports_for_file(file_path: Path, repo_root: Path) -> list[Path]:
    """Parse a Python file with AST and resolve one-hop local module imports.

    Args:
        file_path: Candidate Python file to inspect.
        repo_root: Selected root that resolved imports must not escape.

    Returns:
        Existing resolved local files strictly inside ``repo_root``. Syntax errors and unreadable
        files return an empty list.
    """
    if not file_path.exists() or file_path.suffix.lower() != ".py":
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content, filename=str(file_path))
    except Exception:
        # Syntax error or unparseable file
        return []

    discovered_paths: set[Path] = set()
    candidate_roots = [
        file_path.parent,
        repo_root,
    ]
    if (repo_root / "src").exists() and (repo_root / "src").is_dir():
        candidate_roots.append(repo_root / "src")

    for node in ast.walk(tree):
        module_name = ""
        level = 0

        if isinstance(node, ast.Import):
            for alias in node.names:
                _resolve_module(
                    alias.name, 0, file_path, repo_root, candidate_roots, discovered_paths
                )
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            module_name = node.module or ""
            _resolve_module(
                module_name, level, file_path, repo_root, candidate_roots, discovered_paths
            )
            # Also check if imported names in `from X import Y` correspond to `X/Y.py`
            for alias in node.names:
                sub_mod = f"{module_name}.{alias.name}" if module_name else alias.name
                _resolve_module(
                    sub_mod, level, file_path, repo_root, candidate_roots, discovered_paths
                )

    # Filter to valid files strictly within repo_root, excluding the source file itself
    resolved_files: list[Path] = []
    for p in sorted(discovered_paths):
        if p != file_path.resolve() and p.is_file() and is_safe_child_path(repo_root, p):
            resolved_files.append(p)

    return resolved_files


def _resolve_module(
    module_name: str,
    level: int,
    source_file: Path,
    repo_root: Path,
    candidate_roots: list[Path],
    found: set[Path],
) -> None:
    """Resolve one absolute or relative import target into contained candidates.

    Args:
        module_name: Dotted module portion from an import statement.
        level: Relative-import level, or zero for an absolute import.
        source_file: File that contains the import.
        repo_root: Selected root boundary.
        candidate_roots: Directories considered for absolute imports.
        found: Mutable set receiving resolved local files.
    """
    if not module_name and level == 0:
        return

    rel_parts = module_name.split(".") if module_name else []
    rel_path_str = "/".join(rel_parts)

    if level > 0:
        # Relative import: traverse up (level - 1) directories from source_file.parent
        target_dir = source_file.parent
        for _ in range(level - 1):
            target_dir = target_dir.parent

        _check_candidates(target_dir, rel_path_str, repo_root, found)
    else:
        # Absolute or package-relative import
        for root in candidate_roots:
            _check_candidates(root, rel_path_str, repo_root, found)


def _check_candidates(base_dir: Path, rel_path_str: str, repo_root: Path, found: set[Path]) -> None:
    """Add a contained module file or package initializer to ``found`` when present."""
    if not rel_path_str:
        return

    # Check direct .py file
    py_candidate = (base_dir / f"{rel_path_str}.py").resolve()
    if py_candidate.is_file() and is_safe_child_path(repo_root, py_candidate):
        found.add(py_candidate)
        return

    # Check package __init__.py
    init_candidate = (base_dir / rel_path_str / "__init__.py").resolve()
    if init_candidate.is_file() and is_safe_child_path(repo_root, init_candidate):
        found.add(init_candidate)
        return
