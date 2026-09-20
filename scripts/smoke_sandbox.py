"""Smoke-test drive-root refusal and canonical fixture containment."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pack import pack_repository

CACHE = ROOT / "data" / "cache" / "sandbox_check.json"


def main() -> None:
    """Assert drive refusal, fixture containment, and safe Git fallback behavior."""
    checks: dict[str, object] = {}
    for drive in ("C:\\", "D:\\"):
        ok, message, result = pack_repository(drive, auto_cache=False)
        assert not ok and result is None, f"Drive root must be refused: {drive}"
        checks[drive] = {"refused": True, "message": message}

    fixture = (ROOT / "data" / "fixtures" / "mini_pkg").resolve()
    round_trip = fixture / ".." / "mini_pkg"
    ok, message, result = pack_repository(str(round_trip), auto_cache=False)
    assert ok, message
    assert result is not None
    assert result.repo_path == fixture
    assert all((fixture / item.path).resolve().is_relative_to(fixture) for item in result.manifest)
    checks["fixture_round_trip"] = {
        "input": str(round_trip),
        "resolved_root": str(result.repo_path),
        "stayed_inside_fixture": True,
    }

    ok, message, result = pack_repository(
        str(ROOT), git_refs="missing-ref-for-smoke..HEAD", max_files=1, auto_cache=False
    )
    assert ok, message
    assert result is not None and result.git_error
    assert any("folder fallback" in item.reason for item in result.manifest)
    checks["git_fallback"] = {
        "packed": True,
        "error_shown": result.git_error,
        "used_folder_fallback": True,
    }

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print("PASS: drive roots refused and resolved fixture remained contained")
    print(CACHE)


if __name__ == "__main__":
    main()
