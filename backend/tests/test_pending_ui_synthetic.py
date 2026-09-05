from __future__ import annotations

import json
from pathlib import Path

FIXTURE = (
    Path(__file__).parents[2]
    / "data"
    / "synthetic"
    / "pending-ui-scenarios.json"
)


def test_pending_ui_fixture_covers_operational_distinctions() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = payload["records"]

    assert payload["schema_version"] == "1.0"
    assert {record["scenario"] for record in records} == {
        "pre_release",
        "post_release_hold",
        "technical_failure",
        "partial_release",
    }
    assert all(record["status"] == "open" for record in records)
    assert len({record["workorder_number"] for record in records}) == len(records)
