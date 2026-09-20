"""Smoke test for repo-auditor modules."""

import sys
from os import environ
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.agnes_client import create_agnes_client
from src.audit import parse_findings_json, run_llm_pass, run_static_audit
from src.config import get_config
from src.imports_hop import resolve_one_hop
from src.pack import DEFAULT_PACK_CACHE, gather_repo_files, pack_repository
from src.providers import get_available_providers
from src.safety import is_safe_child_path, validate_relative_path, validate_repo_path


def run_smoke_tests() -> bool:
    print("[1/5] Testing path validation & boundary rules...")

    # Empty path
    valid, _, _ = validate_repo_path("")
    assert not valid, "Empty path should fail"

    valid, traversal_msg, _ = validate_repo_path("D:\\AI\\Github\\repo-auditor\\..")
    assert not valid and "traversal" in traversal_msg.lower()

    assert not validate_relative_path("../secret.txt")[0]
    assert not validate_relative_path("C:\\secret.txt")[0]

    # Drive root rejection (D:\ or C:\)
    valid_d, msg_d, _ = validate_repo_path("D:\\")
    assert not valid_d and "drive root" in msg_d.lower(), (
        f"Drive root D:\\ must be rejected: {msg_d}"
    )

    valid_c, msg_c, _ = validate_repo_path("C:\\")
    assert not valid_c and "drive root" in msg_c.lower(), (
        f"Drive root C:\\ must be rejected: {msg_c}"
    )

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

    fixture = Path("data/fixtures/mini_pkg").resolve()
    valid_folder, _, _ = validate_repo_path(str(fixture))
    assert valid_folder, "Non-Git folders must be accepted"
    assert (fixture / "b.py") in resolve_one_hop(fixture / "c.py", fixture)
    fixture_ok, fixture_msg, fixture_pack = pack_repository(
        str(fixture), budget_chars=10_000, max_files=10, auto_cache=False
    )
    assert fixture_ok, fixture_msg
    assert fixture_pack is not None
    assert "def greet" in fixture_pack.pack_text
    assert 'greetz("Ada")' in fixture_pack.pack_text

    print("[2/5] Testing file packaging (read-only git inspect)...")
    ok, pack_msg, pack_res = gather_repo_files(this_repo, auto_cache=False)
    assert ok, f"Packing failed: {pack_msg}"
    assert pack_res is not None
    assert pack_res.total_files > 0, "Should have packed repo files"
    file_names = [f.rel_path for f in pack_res.files]
    assert "app.py" in file_names, "app.py must be in packed files"
    assert len(pack_res.pack_text) <= 80_000
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
    assert list(providers) == ["Agnes AI"]
    config = get_config()
    assert config.budget_chars == 80_000
    assert config.max_files == 40
    assert config.model == "agnes-3.0-flash"
    with (
        patch.dict(environ, {"AGNESAI_API_KEY": "test-only"}),
        patch("src.agnes_client.OpenAI") as openai_mock,
    ):
        create_agnes_client()
        assert openai_mock.call_args.kwargs["max_retries"] == 3
    print("  [OK] Providers loaded securely without leaking keys")

    security = parse_findings_json(
        '[{"severity":"high","file":"app.py","title":"hardcoded key",'
        '"evidence_span":"line 12","pass_name":"secrets_patterns",'
        '"recommendation":"should be discarded"}]',
        "secrets_patterns",
    )
    assert security == [
        {
            "severity": "high",
            "file": "app.py",
            "title": "Hardcoded key-like assignment",
            "evidence_span": "line 12",
            "pass_name": "secrets_patterns",
            "recommendation": "",
        }
    ]

    class FakeCompletions:
        @staticmethod
        def create(**_kwargs):
            content = (
                '[{"severity":"high","file":"app.py","title":"shell=True",'
                '"evidence_span":"line 1","pass_name":"secrets_patterns",'
                '"recommendation":""},{"severity":"high","file":"invented.py",'
                '"title":"hardcoded key","evidence_span":"line 1",'
                '"pass_name":"secrets_patterns","recommendation":""}]'
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    filtered_security = run_llm_pass(fake_client, "agnes-3.0-flash", "secrets_patterns", pack_res)
    assert filtered_security == [
        {
            "severity": "high",
            "file": "app.py",
            "title": "subprocess shell=True",
            "evidence_span": "line 1",
            "pass_name": "secrets_patterns",
            "recommendation": "",
        }
    ]
    assert DEFAULT_PACK_CACHE.parent == Path(__file__).resolve().parent / "data" / "cache"

    print("[5/5] App module import check...")
    import app

    assert hasattr(app, "PAGES")
    assert app.PAGES == ["Health", "Select", "Pack", "Audit", "Findings"]
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
