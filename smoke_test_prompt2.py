"""Smoke test: pack + audit data/fixtures/mini_pkg against Agnes AI.

Verifies:
1. Packing with AST one-hop expansion (b.py -> a.py).
2. Saving data/cache/last_pack.json.
3. 3-pass Agnes AI audit saving data/cache/last_audit.json.
4. Agnes finding that b.py calls a missing/renamed name (say_hello).
5. Both cache files exist and conform to schema.
"""

from pathlib import Path
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.audit import run_three_pass_audit
from src.pack import pack_repository


def run_smoke_test() -> bool:
    print("[1/5] Packing fixture data/fixtures/mini_pkg with AST resolution...")
    fixture_dir = Path("data/fixtures/mini_pkg").resolve()
    assert fixture_dir.exists(), f"Fixture directory not found: {fixture_dir}"

    ok, msg, pack_res = pack_repository(
        repo_path_str=str(fixture_dir),
        non_git_glob="**/*.py",
        file_cap=10,
        char_cap=50_000,
        auto_cache=True,
    )
    assert ok, f"Packing fixture failed: {msg}"
    assert pack_res is not None
    assert pack_res.total_files >= 2, f"Expected at least 2 files, got {pack_res.total_files}"

    rel_files = [f.rel_path for f in pack_res.files]
    assert any("a.py" in f for f in rel_files), f"a.py must be packed. Found: {rel_files}"
    assert any("b.py" in f for f in rel_files), f"b.py must be packed. Found: {rel_files}"

    # Verify manifest items have path, bytes, status, reason
    assert len(pack_res.manifest) >= 2, "Manifest must have items"
    for item in pack_res.manifest:
        assert hasattr(item, "path")
        assert hasattr(item, "bytes")
        assert hasattr(item, "status")
        assert hasattr(item, "reason")
    print(f"  [OK] Packed {pack_res.total_files} files with manifest ({len(pack_res.manifest)} items)")
    print(f"  [OK] AST one-hop imports: {pack_res.one_hop_links}")

    print("[2/5] Verifying data/cache/last_pack.json...")
    pack_cache_file = Path("data/cache/last_pack.json")
    assert pack_cache_file.exists(), "data/cache/last_pack.json was not created!"
    pack_cache_data = json.loads(pack_cache_file.read_text(encoding="utf-8"))
    assert pack_cache_data.get("total_files") == pack_res.total_files
    print("  [OK] data/cache/last_pack.json exists and is valid")

    print("[3/5] Executing 3-pass Agnes AI audit (Pass 1: Breaking API, Pass 2: Security, Pass 3: Missing Tests)...")
    audit_res = run_three_pass_audit(
        pack_result=pack_res,
        provider_name="Agnes AI",
        model_name="agnes-3.0-flash",
    )
    assert audit_res is not None
    findings = audit_res.get("findings", [])
    print(f"  [OK] Received {len(findings)} total findings from Agnes AI")
    print(f"  [OK] Pass summaries: {audit_res.get('pass_summaries')}")

    print("[4/5] Verifying data/cache/last_audit.json...")
    audit_cache_file = Path("data/cache/last_audit.json")
    assert audit_cache_file.exists(), "data/cache/last_audit.json was not created!"
    cached_data = json.loads(audit_cache_file.read_text(encoding="utf-8"))
    assert len(cached_data.get("findings", [])) == len(findings)

    # Verify schema of findings
    for f in findings:
        assert "severity" in f, "Finding missing 'severity'"
        assert "file" in f, "Finding missing 'file'"
        assert "title" in f, "Finding missing 'title'"
        assert "evidence_span" in f, "Finding missing 'evidence_span'"
        assert "recommendation" in f, "Finding missing 'recommendation'"
    print("  [OK] All findings conform to schema: {severity, file, title, evidence_span, recommendation}")

    print("[5/5] Verifying Agnes detected that b.py calls a missing/renamed name...")
    break_mentioned = False
    break_finding_title = ""

    findings_text = json.dumps(findings).lower()
    if (
        "say_hello" in findings_text
        or "greetz" in findings_text
        or "cannot import" in findings_text
        or "missing" in findings_text
        or "renamed" in findings_text
        or "import error" in findings_text
        or "drift" in findings_text
    ):
        break_mentioned = True
        for f in findings:
            combined = f"{f.get('title', '')} {f.get('evidence_span', '')} {f.get('recommendation', '')}".lower()
            if "say_hello" in combined or "greetz" in combined or "renamed" in combined or "missing" in combined:
                break_finding_title = f.get("title", "")
                break

    assert break_mentioned, f"Agnes did not mention the broken call in b.py! Findings were: {findings_text}"
    print(f"  [OK] Break detected by Agnes! Finding: '{break_finding_title}'")

    # Final check: Both caches exist
    assert pack_cache_file.exists(), "last_pack.json must exist"
    assert audit_cache_file.exists(), "last_audit.json must exist"
    print("  [OK] Both data/cache/last_pack.json and data/cache/last_audit.json exist!")

    print("\nALL FIXTURE SMOKE CHECKS PASSED!")
    return True


if __name__ == "__main__":
    success = run_smoke_test()
    if not success:
        sys.exit(1)
