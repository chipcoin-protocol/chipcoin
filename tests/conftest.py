"""Pytest bootstrap helpers for source-tree runs."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def pytest_configure() -> None:
    """Allow `pytest tests/` to run before an editable install exists."""

    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    if importlib.util.find_spec("chipcoin.crypto.pq._mldsa_native") is not None:
        return
    result = subprocess.run(
        [sys.executable, "setup.py", "build_ext", "--inplace"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise RuntimeError("failed to build the vendored ML-DSA native extension for tests")
