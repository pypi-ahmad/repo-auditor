"""Bounded repository packer with read-only Git diff and one-hop imports."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import git

from src.imports_hop import resolve_one_hop
from src.safety import is_safe_child_path, validate_repo_path

APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACK_CACHE = APP_ROOT / "data" / "cache" / "last_pack.json"
TEXT_EXTENSIONS = {".py", ".md", ".txt", ".toml"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}


@dataclass
class ManifestItem:
    """One candidate file's inclusion decision.

    Attributes:
        path: Root-relative path or a rejected external path.
        bytes: File size observed before packing.
        included: Whether the file contributed to the pack text.
        reason: Selection, exclusion, or truncation explanation.
    """

    path: str
    bytes: int
    included: bool
    reason: str

    @property
    def status(self) -> str:
        """Return the legacy string status used by existing UI and smoke checks.

        Returns:
            ``"included"`` or ``"skipped"`` according to ``included``.
        """
        return "included" if self.included else "skipped"


@dataclass
class PackedFile:
    """Text content and provenance for a file included in a repository pack.

    Attributes:
        rel_path: Path relative to the selected root.
        size_bytes: Original file size before truncation.
        lines: Number of included text lines.
        content: Included text, potentially truncated by the pack budget.
        extension: Lowercase filename extension.
        is_diff_match: Whether Git diff selection chose this file.
        is_ast_import: Whether one-hop import expansion chose this file.
        imported_by: Root-relative file that caused the import expansion.
    """

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
    """Bounded pack, manifest, and metadata used by the Streamlit workflow.

    Attributes:
        repo_path: Resolved selected root.
        is_git: Whether the root contains Git metadata.
        ref_or_glob: Requested Git range or folder-scan descriptor.
        budget_chars: Maximum permitted pack-text size.
        files: Text files included in the pack.
        manifest: Inclusion decisions for candidate files.
        one_hop_links: Local import edges used for expansion.
        pack_text: Header-delimited text sent to audit passes.
        git_error: Read-only Git failure retained when folder fallback was used.
    """

    repo_path: Path
    is_git: bool
    ref_or_glob: str
    budget_chars: int
    files: list[PackedFile] = field(default_factory=list)
    manifest: list[ManifestItem] = field(default_factory=list)
    one_hop_links: dict[str, list[str]] = field(default_factory=dict)
    pack_text: str = ""
    git_error: str = ""

    @property
    def char_cap(self) -> int:
        """Return the compatibility name for the configured character budget.

        Returns:
            Maximum characters allowed in ``pack_text``.
        """
        return self.budget_chars

    @property
    def total_files(self) -> int:
        """Return the number of files included in the pack."""
        return len(self.files)

    @property
    def total_bytes(self) -> int:
        """Return original byte sizes summed across packed files."""
        return sum(item.size_bytes for item in self.files)

    @property
    def total_lines(self) -> int:
        """Return included text lines summed across packed files."""
        return sum(item.lines for item in self.files)

    @property
    def total_chars(self) -> int:
        """Return the exact character count of the bounded pack text."""
        return len(self.pack_text)

    @property
    def token_estimate(self) -> int:
        """Return the app's coarse four-characters-per-token estimate."""
        return self.total_chars // 4


def _walk_supported(root: Path) -> list[Path]:
    """Walk supported text files without following links or excluded directories.

    Args:
        root: Resolved selected repository root.

    Returns:
        Candidate paths with a supported extension, before budget enforcement.
    """
    paths: list[Path] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        dirs[:] = sorted(
            directory
            for directory in dirs
            if directory.lower() not in SKIP_DIRS
            and is_safe_child_path(root, current_path / directory)
        )
        for filename in sorted(files):
            path = current_path / filename
            if path.suffix.lower() in TEXT_EXTENSIONS:
                paths.append(path)
    return paths


def _git_diff_paths(root: Path, refs: str) -> list[Path]:
    """Return root-relative paths from a read-only Git diff.

    Args:
        root: Git repository root.
        refs: Exactly one ``base..head`` revision range.

    Returns:
        Candidate paths named by ``git diff --name-only``.

    Raises:
        ValueError: If refs do not have safe ``base..head`` syntax.
        git.GitCommandError: If Git cannot resolve or diff the requested commits.
    """
    if refs.count("..") != 1 or any(char.isspace() for char in refs):
        raise ValueError("Git refs must use base..head syntax.")
    base_name, head_name = refs.split("..", 1)
    if not base_name or not head_name or base_name.startswith("-") or head_name.startswith("-"):
        raise ValueError("Git refs must use base..head syntax.")

    repo = git.Repo(root, search_parent_directories=False)
    base = repo.commit(base_name).hexsha
    head = repo.commit(head_name).hexsha
    diff_range = f"{base}..{head}"
    names = repo.git.diff(diff_range, name_only=True).splitlines()
    return [root / name.strip() for name in names if name.strip()]


def _safe_relative(root: Path, path: Path) -> str | None:
    """Convert a candidate to a slash-normalized path only when it stays in root."""
    try:
        resolved = path.resolve()
        return resolved.relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None


def _is_binary(path: Path) -> bool:
    """Detect binary content conservatively from the first bytes of a file."""
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(4096)
    except OSError:
        return True


def _pack_piece(relative: str, content: str, remaining: int) -> tuple[str, str, bool]:
    """Add file delimiters and truncate text to the remaining character budget."""
    header = f"===== FILE: {relative} =====\n"
    footer = f"\n===== END FILE: {relative} =====\n"
    full = f"{header}{content}{footer}"
    if len(full) <= remaining:
        return full, content, False
    if remaining <= len(header):
        return "", "", False
    content_part = content[: remaining - len(header)]
    return f"{header}{content_part}", content_part, True


def save_pack_cache(result: PackResult, cache_path: Path | None = None) -> Path:
    """Write the manifest and bounded pack text under the app cache directory.

    Args:
        result: Completed bounded pack to serialize.
        cache_path: Optional explicit cache target for tests or controlled callers.

    Returns:
        Path that received the JSON cache payload.
    """
    target = cache_path or DEFAULT_PACK_CACHE
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": str(result.repo_path),
        "git_refs": result.ref_or_glob if result.is_git else None,
        "budget_chars": result.budget_chars,
        "total_files": result.total_files,
        "total_chars": result.total_chars,
        "manifest": [
            {
                "path": item.path,
                "bytes": item.bytes,
                "included": item.included,
                "reason": item.reason,
            }
            for item in result.manifest
        ],
        "pack_text": result.pack_text,
        "git_error": result.git_error,
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def pack_repository(
    root_path: str,
    git_refs: str | None = None,
    budget_chars: int = 80_000,
    max_files: int = 40,
    *,
    auto_cache: bool = True,
) -> tuple[bool, str, PackResult | None]:
    """Pack bounded text files and their direct local Python imports.

    Args:
        root_path: User-selected local directory.
        git_refs: Optional ``base..head`` range for a read-only Git diff.
        budget_chars: Maximum characters in the generated pack text.
        max_files: Maximum files that may be included.
        auto_cache: Whether to write ``last_pack.json`` after a successful pack.

    Returns:
        Success flag, user-safe status message, and the pack result when successful. Git failures
        retain their error on the result and use a bounded folder-scan fallback.
    """
    valid, message, root = validate_repo_path(root_path)
    if not valid or root is None:
        return False, message, None
    if budget_chars < 1:
        return False, "budget_chars must be positive.", None
    if max_files < 1:
        return False, "max_files must be positive.", None

    is_git = (root / ".git").exists()
    git_error = ""
    selection_reason = "root scan"
    if is_git and git_refs:
        try:
            initial_paths = _git_diff_paths(root, git_refs)
            selection_reason = "git diff"
        except (ValueError, git.BadName, git.GitCommandError, git.InvalidGitRepositoryError) as exc:
            git_error = f"Git diff failed: {exc}"
            initial_paths = _walk_supported(root)
            selection_reason = "folder fallback after git error"
    else:
        initial_paths = _walk_supported(root)

    candidates: list[tuple[Path, str, str]] = []
    seen: set[str] = set()
    one_hop_links: dict[str, list[str]] = {}
    for path in initial_paths:
        relative = _safe_relative(root, path)
        key = relative or str(path)
        if key not in seen:
            seen.add(key)
            candidates.append((path, selection_reason, ""))

        if relative and path.suffix.lower() == ".py":
            imports = resolve_one_hop(path, root)
            for imported in imports:
                imported_relative = imported.relative_to(root).as_posix()
                one_hop_links.setdefault(relative, []).append(imported_relative)
                if imported_relative not in seen:
                    seen.add(imported_relative)
                    candidates.append((imported, f"one-hop import from {relative}", relative))

    manifest: list[ManifestItem] = []
    packed_files: list[PackedFile] = []
    pack_parts: list[str] = []
    used_chars = 0

    for path, reason, imported_by in candidates:
        relative = _safe_relative(root, path)
        if relative is None:
            manifest.append(ManifestItem(str(path), 0, False, "outside selected root"))
            continue
        if len(packed_files) >= max_files:
            size = path.stat().st_size if path.is_file() else 0
            manifest.append(ManifestItem(relative, size, False, "max_files reached"))
            continue
        if not path.is_file():
            manifest.append(ManifestItem(relative, 0, False, "missing or not a file"))
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            manifest.append(
                ManifestItem(relative, path.stat().st_size, False, "unsupported file type")
            )
            continue
        if _is_binary(path):
            manifest.append(ManifestItem(relative, path.stat().st_size, False, "binary content"))
            continue

        size = path.stat().st_size
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            manifest.append(ManifestItem(relative, size, False, f"read error: {exc}"))
            continue

        piece, packed_content, truncated = _pack_piece(relative, content, budget_chars - used_chars)
        if not piece:
            manifest.append(ManifestItem(relative, size, False, "budget_chars reached"))
            continue

        pack_parts.append(piece)
        used_chars += len(piece)
        packed_files.append(
            PackedFile(
                rel_path=relative,
                size_bytes=size,
                lines=len(packed_content.splitlines()),
                content=packed_content,
                extension=path.suffix.lower(),
                is_diff_match=reason == "git diff",
                is_ast_import=bool(imported_by),
                imported_by=imported_by,
            )
        )
        included_reason = f"{reason}; truncated to budget" if truncated else reason
        manifest.append(ManifestItem(relative, size, True, included_reason))

    result = PackResult(
        repo_path=root,
        is_git=is_git,
        ref_or_glob=git_refs or "all supported files",
        budget_chars=budget_chars,
        files=packed_files,
        manifest=manifest,
        one_hop_links=one_hop_links,
        pack_text="".join(pack_parts),
        git_error=git_error,
    )
    if auto_cache:
        save_pack_cache(result)
    message = f"Packed {result.total_files} files ({result.total_chars:,} chars)."
    if git_error:
        message = f"{message} Folder fallback used because {git_error}"
    return True, message, result


gather_repo_files = pack_repository
