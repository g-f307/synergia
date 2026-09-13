from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_data_governance import (  # noqa: E402
    validate_no_secret_material,
    validate_policy,
    validate_runbooks,
)


def test_retention_policy_covers_all_data_groups() -> None:
    validate_policy()


def test_alerts_reference_executable_runbooks() -> None:
    validate_runbooks()


def test_public_recovery_material_contains_no_credentials() -> None:
    validate_no_secret_material()
