from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "npm_production_audit",
    ROOT / "scripts/audit-public-mainnet-npm-production.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_accepts_zero_vulnerabilities() -> None:
    assert MODULE.vulnerability_total({"metadata": {"vulnerabilities": {"total": 0}}}) == 0


@pytest.mark.parametrize("report", [
    {},
    {"metadata": {}},
    {"metadata": {"vulnerabilities": {"total": "0"}}},
    {"metadata": {"vulnerabilities": {"total": -1}}},
])
def test_rejects_incomplete_or_invalid_reports(report: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        MODULE.vulnerability_total(report)
