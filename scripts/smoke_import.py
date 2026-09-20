"""Import the application and core modules from a script entry point."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import src.audit
import src.pack

assert app.PAGES == ["Health", "Select", "Pack", "Audit", "Findings"]
assert hasattr(src.audit, "run_three_pass_audit")
assert hasattr(src.pack, "pack_repository")
print("PASS: imported app, src.pack, and src.audit")
