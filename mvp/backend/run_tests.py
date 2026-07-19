"""Run backend unit tests from the backend directory."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

# Silence service logs before any service modules are imported.
os.environ["SERVICE_LOG_ENABLED"] = "0"

BACKEND_DIR = Path(__file__).resolve().parent


def main() -> int:
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    suite = unittest.defaultTestLoader.discover(
        start_dir=str(BACKEND_DIR / "tests"),
        pattern="test_*.py",
        top_level_dir=str(BACKEND_DIR),
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
