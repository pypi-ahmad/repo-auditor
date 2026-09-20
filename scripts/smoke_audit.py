"""Live smoke: load the fixture pack cache and call Agnes exactly three times."""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.audit import DEFAULT_AUDIT_CACHE, run_three_pass_audit
from src.pack import ManifestItem, PackedFile, PackResult

PACK_CACHE = PROJECT_ROOT / "data" / "cache" / "last_pack.json"
REQUIRED_FIELDS = {
    "severity",
    "file",
    "title",
    "evidence_span",
    "pass_name",
    "recommendation",
}


def load_cached_pack() -> PackResult:
    """Reconstruct the fixture PackResult from ``last_pack.json`` without repacking.

    Returns:
        Mini-fixture pack reconstructed from the cache for the live audit smoke.

    Raises:
        AssertionError: If the cache was not created from ``mini_pkg``.
    """
    payload = json.loads(PACK_CACHE.read_text(encoding="utf-8"))
    if Path(payload["root"]).name != "mini_pkg":
        raise AssertionError("last_pack.json must be generated from data/fixtures/mini_pkg.")
    pack_text = str(payload["pack_text"])
    manifest = [ManifestItem(**row) for row in payload["manifest"]]
    files: list[PackedFile] = []
    for item in manifest:
        if not item.included:
            continue
        pattern = rf"===== FILE: {re.escape(item.path)} =====\n(.*?)(?:\n===== END FILE: {re.escape(item.path)} =====\n|\Z)"
        match = re.search(pattern, pack_text, re.DOTALL)
        content = match.group(1) if match else ""
        files.append(
            PackedFile(
                rel_path=item.path,
                size_bytes=item.bytes,
                lines=len(content.splitlines()),
                content=content,
                extension=Path(item.path).suffix.lower(),
            )
        )
    return PackResult(
        repo_path=Path(payload["root"]),
        is_git=bool(payload.get("git_refs")),
        ref_or_glob=payload.get("git_refs") or "all supported files",
        budget_chars=int(payload["budget_chars"]),
        files=files,
        manifest=manifest,
        pack_text=pack_text,
    )


def main() -> None:
    """Run the three-call live Agnes smoke against the cached mini fixture."""
    if not PACK_CACHE.exists():
        raise RuntimeError("data/cache/last_pack.json is missing; run scripts/smoke_pack.py first.")
    pack = load_cached_pack()
    if "def greet" not in pack.pack_text or "greetz" not in pack.pack_text:
        raise AssertionError("last_pack.json is not the expected mini_pkg pack.")

    result = run_three_pass_audit(pack)
    findings = result["findings"]
    assert DEFAULT_AUDIT_CACHE.exists(), "data/cache/last_audit.json was not created."
    assert set(result["pass_summaries"]) == {"api_drift", "secrets_patterns", "tests"}
    assert all(set(finding) == REQUIRED_FIELDS for finding in findings)
    assert len({(f["file"].casefold(), f["title"].casefold()) for f in findings}) == len(findings)
    drift_text = json.dumps(
        [finding for finding in findings if finding["pass_name"] == "api_drift"]
    ).lower()
    assert "b.py" in drift_text and "greetz" in drift_text, (
        "Agnes did not report that b.py calls the missing greetz name."
    )
    print(f"PASS: 3 Agnes calls produced {len(findings)} deduplicated findings")
    print(DEFAULT_AUDIT_CACHE)


if __name__ == "__main__":
    main()
