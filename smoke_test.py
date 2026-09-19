"""Smoke test for repo-auditor modules."""

from pathlib import Path
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.audit import run_static_audit
from src.pack import gather_repo_files
from src.providers import get_available_providers
from src.safety import is_safe_child_path, validate_repo_path


def run_smoke_tests() -> bool:
    print("[1/5] Testing path validation & boundary rules...")

    # Empty path
    valid, msg, _ = validate_repo_path("")
    assert not valid, "Empty path should fail"

    # Drive root rejection (D:\ or C:\)
    valid_d, msg_d, _ = validate_repo_path("D:\\")
    assert not valid_d and "drive root" in msg_d.lower(), f"Drive root D:\\ must be rejected: {msg_d}"

    valid_c, msg_c, _ = validate_repo_path("C:\\")
    assert not valid_c and "drive root" in msg_c.lower(), f"Drive root C:\\ must be rejected: {msg_c}"

    # Valid current repo
    this_repo = str(Path(__file__).parent.resolve())
    valid_repo, msg_repo, res_path = validate_repo_path(this_repo)
    assert valid_repo, f"Current repo validation failed: {msg_repo}"
    assert res_path is not None
    print(f"  [OK] Path safety verified: {res_path}")

    # Boundary check
    assert is_safe_child_path(res_path, res_path / "app.py")
    assert not is_safe_child_path(res_path, Path("D:\\AI\\other-repo"))
    print("  [OK] Boundary checks verified")

    print("[2/5] Testing file packaging (read-only git inspect)...")
    ok, pack_msg, pack_res = gather_repo_files(this_repo)
    assert ok, f"Packing failed: {pack_msg}"
    assert pack_res is not None
    assert pack_res.total_files > 0, "Should have packed repo files"
    file_names = [f.rel_path for f in pack_res.files]
    assert "app.py" in file_names, "app.py must be in packed files"
    print(f"  [OK] Packed {pack_res.total_files} files ({pack_res.total_lines} lines)")

    print("[3/5] Testing static audit suite...")
    audit_report = run_static_audit(pack_res)
    assert audit_report.total_files_audited == pack_res.total_files
    print(f"  [OK] Audit completed with {len(audit_report.findings)} findings")

    print("[4/5] Testing provider configuration...")
    providers = get_available_providers()
    assert "Agnes AI" in providers, "Agnes AI must be present"
    agnes = providers["Agnes AI"]
    assert agnes.models == ["agnes-3.0-flash"]
    assert agnes.base_url == "https://apihub.agnes-ai.com/v1"
    assert agnes.has_api_key is True, "AGNESAI_API_KEY expected in environment"
    print("  [OK] Providers loaded securely without leaking keys")

    print("[5/5] App module import check...")
    import app
    assert hasattr(app, "PAGES")
    print("  [OK] app.py imports cleanly")

    print("\nALL SMOKE TESTS PASSED!")
    return True


if __name__ == "__main__":
    try:
        success = run_smoke_tests()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"FAILED assertion: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"FAILED with unexpected exception: {e}")
        sys.exit(1)
