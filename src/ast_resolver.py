"""Python AST-based local import resolver for one-hop dependency discovery."""

import ast
from pathlib import Path
from typing import List, Set

from src.safety import is_safe_child_path


def get_local_imports_for_file(file_path: Path, repo_root: Path) -> List[Path]:
    """Parses a Python file with ast and resolves one-hop local module imports.

    Returns a list of resolved existing Path objects strictly within repo_root.
    """
    if not file_path.exists() or file_path.suffix.lower() != ".py":
        return []

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(content, filename=str(file_path))
    except Exception:
        # Syntax error or unparseable file
        return []

    discovered_paths: Set[Path] = set()
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
                _resolve_module(alias.name, 0, file_path, repo_root, candidate_roots, discovered_paths)
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            module_name = node.module or ""
            _resolve_module(module_name, level, file_path, repo_root, candidate_roots, discovered_paths)
            # Also check if imported names in `from X import Y` correspond to `X/Y.py`
            for alias in node.names:
                sub_mod = f"{module_name}.{alias.name}" if module_name else alias.name
                _resolve_module(sub_mod, level, file_path, repo_root, candidate_roots, discovered_paths)

    # Filter to valid files strictly within repo_root, excluding the source file itself
    resolved_files: List[Path] = []
    for p in sorted(discovered_paths):
        if p != file_path.resolve() and p.is_file() and is_safe_child_path(repo_root, p):
            resolved_files.append(p)

    return resolved_files


def _resolve_module(
    module_name: str,
    level: int,
    source_file: Path,
    repo_root: Path,
    candidate_roots: List[Path],
    found: Set[Path],
) -> None:
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


def _check_candidates(base_dir: Path, rel_path_str: str, repo_root: Path, found: Set[Path]) -> None:
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
