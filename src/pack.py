"""File gathering, AST import expansion, and repository packaging logic."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import git

from src.ast_resolver import get_local_imports_for_file
from src.safety import is_safe_child_path

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".bmp", ".webp",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".iso", ".msi",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".whl",
    ".pyc", ".pyd", ".pyo", ".db", ".sqlite", ".sqlite3",
    ".pdf", ".docx", ".xlsx", ".pptx", ".parquet", ".arrow",
}

DEFAULT_SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".idea", ".vscode", "data"
}


@dataclass
class ManifestItem:
    path: str
    bytes: int
    status: str  # "included" or "skipped"
    reason: str


@dataclass
class PackedFile:
    rel_path: str
    size_bytes: int
    lines: int
    content: str
    extension: str
    is_diff_match: bool = False
    is_ast_import: bool = False
    imported_by: str = ""


@dataclass
class PackResult:
    repo_path: Path
    is_git: bool
    ref_or_glob: str
    char_cap: int
    files: List[PackedFile] = field(default_factory=list)
    manifest: List[ManifestItem] = field(default_factory=list)
    one_hop_links: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)

    @property
    def total_lines(self) -> int:
        return sum(f.lines for f in self.files)

    @property
    def total_chars(self) -> int:
        return sum(len(f.content) for f in self.files)

    @property
    def token_estimate(self) -> int:
        return self.total_chars // 4


def is_binary_content(sample_bytes: bytes) -> bool:
    """Detect if raw sample bytes indicate binary content."""
    return b"\x00" in sample_bytes


def resolve_git_ref(repo: git.Repo, user_ref: Optional[str] = None) -> Tuple[str, List[str]]:
    """Resolves target git ref and returns (resolved_ref_name, list_of_changed_files)."""
    # 1. User-supplied ref
    if user_ref and user_ref.strip():
        ref = user_ref.strip()
        try:
            diff_out = repo.git.diff(ref, name_only=True)
            return ref, [l.strip() for l in diff_out.splitlines() if l.strip()]
        except Exception:
            pass

    # 2. origin/HEAD
    try:
        repo.git.rev_parse("origin/HEAD")
        diff_out = repo.git.diff("origin/HEAD", name_only=True)
        return "origin/HEAD", [l.strip() for l in diff_out.splitlines() if l.strip()]
    except Exception:
        pass

    # 3. HEAD~1
    try:
        repo.git.rev_parse("HEAD~1")
        diff_out = repo.git.diff("HEAD~1", name_only=True)
        return "HEAD~1", [l.strip() for l in diff_out.splitlines() if l.strip()]
    except Exception:
        pass

    # 4. Fallback to uncommitted changes vs HEAD
    try:
        diff_out = repo.git.diff("HEAD", name_only=True)
        files = [l.strip() for l in diff_out.splitlines() if l.strip()]
        if files:
            return "HEAD (working diff)", files
    except Exception:
        pass

    # 5. If no diff vs ref exists (e.g. brand new repository), fallback to all tracked files
    try:
        tracked = [l.strip() for l in repo.git.ls_files().splitlines() if l.strip()]
        return "all-tracked (initial commit)", tracked
    except Exception:
        return "none", []


def save_pack_cache(result: PackResult, cache_path: Optional[Path] = None) -> Path:
    """Saves pack manifest and metadata to data/cache/last_pack.json."""
    target = cache_path or Path("data/cache/last_pack.json")
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "repo_path": str(result.repo_path),
        "is_git": result.is_git,
        "ref_or_glob": result.ref_or_glob,
        "char_cap": result.char_cap,
        "total_files": result.total_files,
        "total_lines": result.total_lines,
        "total_chars": result.total_chars,
        "total_bytes": result.total_bytes,
        "one_hop_links": result.one_hop_links,
        "manifest": [
            {
                "path": item.path,
                "bytes": item.bytes,
                "status": item.status,
                "reason": item.reason,
            }
            for item in result.manifest
        ],
        "files": [
            {
                "rel_path": f.rel_path,
                "bytes": f.size_bytes,
                "lines": f.lines,
                "is_diff_match": f.is_diff_match,
                "is_ast_import": f.is_ast_import,
                "imported_by": f.imported_by,
            }
            for f in result.files
        ],
    }

    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def pack_repository(
    repo_path_str: str,
    user_ref: Optional[str] = None,
    non_git_glob: Optional[str] = None,
    explicit_files: Optional[List[str]] = None,
    file_cap: int = 50,
    char_cap: int = 120_000,
    max_size_kb: int = 500,
    auto_cache: bool = True,
) -> Tuple[bool, str, Optional[PackResult]]:
    """Gathers repository files with one-hop AST local import expansion and character cap."""
    clean_path_str = repo_path_str.strip()
    if not clean_path_str:
        return False, "Repository path cannot be empty.", None

    repo_path = Path(clean_path_str).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        return False, f"Directory does not exist: {repo_path}", None

    # Refuse drive root
    if repo_path == Path(repo_path.anchor) or len(repo_path.parts) <= 1:
        return False, f"Refusing to scan drive root ({repo_path}).", None

    is_git = (repo_path / ".git").exists()
    manifest: List[ManifestItem] = []
    initial_candidates: List[Tuple[str, str]] = []  # (rel_path, source_reason)
    target_ref_or_glob = ""

    # 1. Explicit file list if provided
    if explicit_files:
        target_ref_or_glob = "explicit file list"
        for item in explicit_files:
            clean_item = item.strip().replace("\\", "/")
            if clean_item:
                initial_candidates.append((clean_item, "Explicit file candidate"))

    # 2. Git mode when .git exists and no explicit file list provided
    elif is_git:
        try:
            repo = git.Repo(repo_path)
            ref_name, changed_files = resolve_git_ref(repo, user_ref)
            target_ref_or_glob = ref_name

            # Include untracked files as well
            untracked = list(repo.untracked_files)
            combined_initial = list(dict.fromkeys(changed_files + untracked))

            for f in combined_initial:
                reason = f"Changed vs {ref_name}" if f in changed_files else "Untracked file"
                initial_candidates.append((f, reason))
        except Exception as exc:
            return False, f"Git inspection failed: {exc}", None

    # 3. Non-git directory: glob pattern with file cap
    else:
        glob_pattern = non_git_glob.strip() if non_git_glob else "**/*.py"
        target_ref_or_glob = glob_pattern
        try:
            matched_paths = list(repo_path.glob(glob_pattern))
            for p in matched_paths:
                if p.is_file() and is_safe_child_path(repo_path, p):
                    rel = p.relative_to(repo_path).as_posix()
                    initial_candidates.append((rel, f"Matched glob '{glob_pattern}'"))
                    if len(initial_candidates) >= file_cap:
                        break
        except Exception as exc:
            return False, f"Glob evaluation '{glob_pattern}' failed: {exc}", None

    # One-hop AST local import resolution for Python files
    expanded_candidates: List[Tuple[str, str, str]] = []  # (rel_path, reason, imported_by)
    visited_rel_paths: Set[str] = set()
    one_hop_links: Dict[str, List[str]] = {}

    for rel_path, reason in initial_candidates:
        clean_rel = rel_path.replace("\\", "/").strip()
        if clean_rel not in visited_rel_paths:
            visited_rel_paths.add(clean_rel)
            expanded_candidates.append((clean_rel, reason, ""))

            # If Python file, resolve one-hop local imports
            full_path = (repo_path / clean_rel).resolve()
            if full_path.suffix.lower() == ".py" and full_path.is_file():
                local_deps = get_local_imports_for_file(full_path, repo_path)
                for dep in local_deps:
                    dep_rel = dep.relative_to(repo_path).as_posix()
                    one_hop_links.setdefault(clean_rel, []).append(dep_rel)
                    if dep_rel not in visited_rel_paths:
                        visited_rel_paths.add(dep_rel)
                        expanded_candidates.append(
                            (dep_rel, f"One-hop AST import from {clean_rel}", clean_rel)
                        )

    # Process and pack candidate files respecting char_cap and max_size_kb
    packed_files: List[PackedFile] = []
    current_total_chars = 0
    max_bytes = max_size_kb * 1024

    for rel_path, reason, imported_by in expanded_candidates:
        full_path = (repo_path / rel_path).resolve()

        if not is_safe_child_path(repo_path, full_path):
            manifest.append(ManifestItem(path=rel_path, bytes=0, status="skipped", reason="Path traversal outside root"))
            continue

        if not full_path.exists() or not full_path.is_file():
            manifest.append(ManifestItem(path=rel_path, bytes=0, status="skipped", reason="File missing or not regular file"))
            continue

        parts = full_path.relative_to(repo_path).parts
        if any(skip in parts for skip in DEFAULT_SKIP_DIRS):
            manifest.append(ManifestItem(path=rel_path, bytes=0, status="skipped", reason="Ignored directory"))
            continue

        ext = full_path.suffix.lower()
        if ext in BINARY_EXTENSIONS:
            manifest.append(ManifestItem(path=rel_path, bytes=full_path.stat().st_size, status="skipped", reason=f"Binary extension ({ext})"))
            continue

        size = full_path.stat().st_size
        if size > max_bytes:
            manifest.append(ManifestItem(path=rel_path, bytes=size, status="skipped", reason=f"Exceeds max file size ({size/1024:.1f} KB > {max_size_kb} KB)"))
            continue

        # Read content
        try:
            with open(full_path, "rb") as f:
                sample = f.read(2048)
                if is_binary_content(sample):
                    manifest.append(ManifestItem(path=rel_path, bytes=size, status="skipped", reason="Binary content detected"))
                    continue
                f.seek(0)
                raw = f.read()

            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                content = raw.decode("latin-1")

            # Check character cap
            file_char_count = len(content)
            if current_total_chars + file_char_count > char_cap:
                manifest.append(
                    ManifestItem(
                        path=rel_path,
                        bytes=size,
                        status="skipped",
                        reason=f"Exceeds character cap ({current_total_chars + file_char_count:,} > {char_cap:,})",
                    )
                )
                continue

            current_total_chars += file_char_count
            lines = len(content.splitlines())

            packed_files.append(
                PackedFile(
                    rel_path=rel_path,
                    size_bytes=size,
                    lines=lines,
                    content=content,
                    extension=ext,
                    is_diff_match=("Changed" in reason or "Untracked" in reason or "Explicit" in reason),
                    is_ast_import=bool(imported_by),
                    imported_by=imported_by,
                )
            )
            manifest.append(ManifestItem(path=rel_path, bytes=size, status="included", reason=reason))

        except Exception as exc:
            manifest.append(ManifestItem(path=rel_path, bytes=size, status="skipped", reason=f"Read error: {exc}"))

    result = PackResult(
        repo_path=repo_path,
        is_git=is_git,
        ref_or_glob=target_ref_or_glob,
        char_cap=char_cap,
        files=packed_files,
        manifest=manifest,
        one_hop_links=one_hop_links,
    )

    if auto_cache:
        save_pack_cache(result)

    return True, f"Packed {result.total_files} files ({result.total_chars:,} chars, cap: {char_cap:,}).", result


# Backward-compatible alias
gather_repo_files = pack_repository
