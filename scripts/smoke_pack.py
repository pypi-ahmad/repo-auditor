"""Smoke test the fixture packer without calling Agnes AI."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pack import DEFAULT_PACK_CACHE, pack_repository


def main() -> None:
    """Pack the mini fixture and assert its bounded cache contract without Agnes."""
    fixture = ROOT / "data" / "fixtures" / "mini_pkg"
    ok, message, result = pack_repository(
        str(fixture),
        budget_chars=80_000,
        max_files=40,
        auto_cache=True,
    )
    assert ok, message
    assert result is not None
    assert "def greet" in result.pack_text
    assert "greetz" in result.pack_text
    assert len(result.pack_text) <= 80_000

    cached = json.loads(DEFAULT_PACK_CACHE.read_text(encoding="utf-8"))
    assert cached["pack_text"] == result.pack_text
    assert all({"path", "bytes", "included", "reason"} <= set(row) for row in cached["manifest"])
    print(f"PASS: packed {result.total_files} files into {result.total_chars} characters")
    print(DEFAULT_PACK_CACHE)


if __name__ == "__main__":
    main()
