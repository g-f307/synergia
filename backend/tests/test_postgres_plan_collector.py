from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from collect_postgres_query_plans import (  # noqa: E402
    _nearest_rank,
    _queries,
    _summarize,
)


def test_plan_percentiles_use_nearest_rank() -> None:
    durations = [1, 2, 3, 4, 100]
    assert _nearest_rank(durations, 0.50) == 3
    assert _nearest_rank(durations, 0.95) == 100
    assert _nearest_rank(durations, 0.99) == 100


def test_plan_summary_preserves_scans_buffers_and_disk_spills() -> None:
    summary = _summarize(
        {
            "Execution Time": 12.5,
            "Planning Time": 0.2,
            "Plan": {
                "Node Type": "Sort",
                "Actual Rows": 10,
                "Shared Hit Blocks": 11,
                "Shared Read Blocks": 2,
                "Temp Written Blocks": 1,
                "Sort Method": "external merge",
                "Sort Space Type": "Disk",
                "Sort Space Used": 32,
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Relation Name": "serials",
                        "Index Name": "idx_serials_number",
                        "Actual Rows": 10,
                        "Actual Loops": 1,
                    }
                ],
            },
        }
    )
    assert summary["execution_ms"] == 12.5
    assert summary["shared_read_blocks"] == 2
    assert summary["temp_written_blocks"] == 1
    assert summary["scans"][0]["index"] == "idx_serials_number"
    assert summary["sorts"][0]["space_type"] == "Disk"


def test_critical_queries_bind_synthetic_scope_and_parameters() -> None:
    samples = {
        "workorders": {"median": "SYN-WO-000850"},
        "lots": {"median": "SYN-LOT-000850"},
        "serials": {"median": "SYN-SER-00011000"},
    }
    queries = _queries(
        "synthetic-execution",
        "63000000-0000-4000-8000-000000000011",
        samples,
        datetime(2026, 9, 15, tzinfo=UTC),
    )
    assert len(queries) == 15
    for name, sql, parameters in queries:
        assert sql.count("%s") == len(parameters), name
        assert "synergia." in sql
        if name.endswith("detail") or name.startswith("search_"):
            assert "e.organization_id = %s" in sql
            assert "completed_with_errors" in sql
