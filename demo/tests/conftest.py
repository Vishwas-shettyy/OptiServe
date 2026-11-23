"""Make demo/ and demo/demo_app importable. Run: backend/.venv/bin/python -m pytest -q demo/tests"""

import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(DEMO), str(DEMO / "demo_app")]
