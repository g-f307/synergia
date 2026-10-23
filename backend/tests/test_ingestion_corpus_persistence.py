from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ingestion_corpus import (  # noqa: E402
    CORPUS,
    decision,
    digest,
    execute,
    golden,
    verify_manifest,
    workorder,
)

from app.authorization import ActorContext, get_actor_context  # noqa: E402
from app.business_rules import RULE_CATALOG  # noqa: E402
from app.execution import PIPELINE_VERSION  # noqa: E402
from app.imports import (  # noqa: E402
    PostgresImportRepository,
    get_repository,
)
from app.main import app  # noqa: E402
from app.queries import PostgresQueryRepository  # noqa: E402

pytestmark = pytest.mark.integration
CASES = verify_manifest()["cases"]
TABLES = (
    "pending_items",
    "holds",
    "oqc_decisions",
    "classifications",
    "rule_evaluations",
    "consolidated_field_provenance",
    "audit_events",
    "pipeline_issues",
    "pipeline_summaries",
    "normalized_records",
    "imported_records",
    "serials",
    "lots",
    "workorders",
    "organizations",
    "execution_idempotency",
    "source_files",
    "file_inspections",
    "execution_state_transitions",
)


class CorpusDatabase:
    def __init__(self, database):
        self.database = database
        self.repository = PostgresImportRepository(database)
        self.ids = []
        self.orgs = []
        self.users = []

    def organization(self):
        identifier = uuid4()
        with psycopg.connect(self.database) as conn:
            conn.execute(
                "INSERT INTO synergia.iam_organizations "
                "(id, organization_code, display_name) "
                "VALUES (%s, %s, 'Synthetic corpus')",
                (identifier, "corpus-" + identifier.hex),
            )
        self.orgs.append(identifier)
        return identifier

    def attach(self, identifier, name):
        case = (
            name
            if isinstance(name, dict)
            else next(c for c in CASES if c["id"] == name)
        )
        path = CORPUS / case["input"]
        file_id, duplicate = self.repository.claim_file(
            identifier,
            source=case["source"],
            file_name=path.name,
            extension="xlsx",
            size_bytes=path.stat().st_size,
            digest=digest(path.read_bytes()),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            storage_key=f"accepted/{identifier}/synthetic.xlsx",
        )
        assert duplicate is None
        return identifier, file_id, case

    def seed(self, name, org=None):
        case = (
            name
            if isinstance(name, dict)
            else next(c for c in CASES if c["id"] == name)
        )
        identifier = "corpus-" + uuid4().hex
        self.repository.start(
            identifier,
            case["source"],
            "technical",
            "synthetic",
            organization_id=org or self.organization(),
        )
        self.ids.append(identifier)
        return self.attach(identifier, name)

    def run(self, seeded):
        identifier, file_id, case = seeded
        return execute(
            CORPUS / case["input"],
            case["source"],
            repository=self.repository,
            execution_id=identifier,
            source_file_id=file_id,
        )

    def reconcile(self, seeded, report, result):
        identifier, file_id, case = seeded
        with psycopg.connect(self.database) as conn:
            actual = {}
            for kind, table in (
                ("imported", "imported_records"),
                ("normalized", "normalized_records"),
            ):
                actual[kind] = dict(
                    conn.execute(
                        f"SELECT sheet_name, count(*) FROM synergia.{table} "
                        "WHERE execution_id = %s AND source_file_id = %s "
                        "GROUP BY sheet_name",
                        (identifier, file_id),
                    ).fetchall()
                )
            for kind in actual:
                assert actual[kind] == {
                    sheet["sheet"]: sheet[kind]
                    for sheet in report["sheets"]
                    if sheet[kind]
                }
            expected_values = sorted(
                [
                    (
                        r["sheet"],
                        r["row"],
                        r["original_values"],
                        r["values"],
                        r["transformations"],
                    )
                    for r in result["normalized_records"]
                ],
                key=lambda row: row[:2],
            )
            assert self.snapshot(identifier) == expected_values
            persisted_imports = conn.execute(
                "SELECT sheet_name, row_number, original_values "
                "FROM synergia.imported_records "
                "WHERE execution_id = %s ORDER BY sheet_name, row_number",
                (identifier,),
            ).fetchall()
            assert persisted_imports == sorted(
                [
                    (r["sheet"], r["row"], r["original_values"])
                    for r in result["imported_records"]
                ],
                key=lambda row: row[:2],
            )
            fields = (
                "workorder_number",
                "planned_quantity",
                "produced_quantity",
                "received_quantity",
                "released_quantity",
                "pending_quantity",
                "retained_quantity",
                "partially_released",
            )
            persisted_workorders = conn.execute(
                f"SELECT {', '.join(fields)} FROM synergia.workorders "
                "WHERE execution_id = %s ORDER BY workorder_number",
                (identifier,),
            ).fetchall()
            assert persisted_workorders == sorted(
                [
                    tuple(w.get(key) for key in fields)
                    for w in result["processing"]["consolidation"]["workorders"]
                ],
                key=lambda row: row[0],
            )
            for table, count_key in (
                ("lots", "consolidated_lots"),
                ("serials", "consolidated_serials"),
                ("classifications", "classifications"),
            ):
                assert (
                    conn.execute(
                        f"SELECT count(*) FROM synergia.{table} "
                        "WHERE execution_id = %s",
                        (identifier,),
                    ).fetchone()[0]
                    == (result["processing"]["summary"][count_key])
                )
            assert self.repository.get(identifier)["status"] == report["status"]
            rejected = conn.execute(
                "SELECT count(*) FROM synergia.imported_records "
                "WHERE execution_id = %s AND processing_status = 'rejected'",
                (identifier,),
            ).fetchone()[0]
            assert rejected == sum(s["rejected"] for s in report["sheets"])
            source = conn.execute(
                "SELECT source, content_hash FROM synergia.source_files WHERE id = %s",
                (file_id,),
            ).fetchone()
            assert source == (case["source"], case["input_sha256"])
            invalid_provenance = conn.execute(
                "SELECT count(*) FROM synergia.normalized_records "
                "WHERE execution_id = %s "
                "AND (source_file_id <> %s OR row_number IS NULL "
                "OR transformations -> 0 ->> 'adapter' IS NULL)",
                (identifier, file_id),
            ).fetchone()[0]
            assert invalid_provenance == 0

    def snapshot(self, identifier):
        with psycopg.connect(self.database) as conn:
            return conn.execute(
                "SELECT sheet_name, row_number, original_values, normalized_values, "
                "transformations FROM synergia.normalized_records "
                "WHERE execution_id = %s ORDER BY sheet_name, row_number",
                (identifier,),
            ).fetchall()

    def cleanup(self):
        with psycopg.connect(self.database) as conn:
            for identifier in reversed(self.ids):
                for table in TABLES:
                    conn.execute(
                        f"DELETE FROM synergia.{table} WHERE execution_id = %s",
                        (identifier,),
                    )
                conn.execute(
                    "DELETE FROM synergia.executions WHERE id = %s", (identifier,)
                )
            for org in self.orgs:
                conn.execute(
                    "UPDATE synergia.iam_organizations SET is_active = false, "
                    "deactivated_at = now() WHERE id = %s",
                    (org,),
                )
            for user in self.users:
                conn.execute(
                    "UPDATE synergia.identity_users SET status = 'inactive', "
                    "deactivated_at = now() WHERE id = %s",
                    (user,),
                )


@pytest.fixture
def corpus_db():
    harness = CorpusDatabase(os.environ["DATABASE_URL"])
    try:
        yield harness
    finally:
        harness.cleanup()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_every_frozen_case_reconciles_with_real_persistence(corpus_db, case):
    seeded = corpus_db.seed(case["id"])
    assert (
        corpus_db.repository.claim_processing(seeded[0], [case["input_sha256"]]) is None
    )
    report, result = corpus_db.run(seeded)
    assert golden(report, result) == json.loads((CORPUS / case["golden"]).read_text())
    corpus_db.reconcile(seeded, report, result)
    snapshot = corpus_db.snapshot(seeded[0])
    with pytest.raises(RuntimeError, match="não está apta"):
        corpus_db.repository.commit_pipeline(seeded[0], result)
    assert corpus_db.snapshot(seeded[0]) == snapshot


@pytest.mark.parametrize("name", ["wo-composite", "td-mixed"])
def test_simultaneous_same_file_runs_have_one_owner_and_one_result(corpus_db, name):
    org = corpus_db.organization()
    seeds = [corpus_db.seed(name, org) for _ in range(2)]
    barrier = Barrier(2)

    def attempt(seeded):
        barrier.wait(timeout=15)
        duplicate = corpus_db.repository.claim_processing(
            seeded[0], [seeded[2]["input_sha256"]]
        )
        if duplicate:
            corpus_db.repository.abort_claim(seeded[0], "duplicate_file")
            return duplicate, None
        report, result = corpus_db.run(seeded)
        corpus_db.reconcile(seeded, report, result)
        return seeded[0], report

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, seeded) for seeded in seeds]
        results = [future.result(timeout=60) for future in futures]
    assert len({item[0] for item in results}) == 1
    assert sum(item[1] is not None for item in results) == 1
    loser = next(s for s in seeds if s[0] != results[0][0])
    assert corpus_db.snapshot(loser[0]) == []
    assert corpus_db.repository.get(loser[0])["status"] == "failed"


@pytest.mark.parametrize(
    "table,column",
    [
        ("normalized_records", "normalized_values"),
        ("imported_records", "original_values"),
    ],
)
def test_reconciliation_detects_corrupted_content_without_count_changes(
    corpus_db, table, column
):
    seeded = corpus_db.seed("td-clean")
    report, result = corpus_db.run(seeded)
    corpus_db.reconcile(seeded, report, result)
    with psycopg.connect(corpus_db.database) as conn:
        conn.execute(
            f"UPDATE synergia.{table} SET {column} = "
            f"{column} || '{{\"injected\":true}}'::jsonb WHERE execution_id = %s",
            (seeded[0],),
        )
    with pytest.raises(AssertionError):
        corpus_db.reconcile(seeded, report, result)


@pytest.mark.parametrize("names", [("wo-nfp", "wo-owm"), ("td-clean", "td-mixed")])
def test_simultaneous_distinct_files_preserve_each_organizations_results(
    corpus_db, names
):
    seeds = [corpus_db.seed(name) for name in names]
    barrier = Barrier(2)

    def attempt(seeded):
        barrier.wait(timeout=15)
        assert (
            corpus_db.repository.claim_processing(
                seeded[0], [seeded[2]["input_sha256"]]
            )
            is None
        )
        report, result = corpus_db.run(seeded)
        corpus_db.reconcile(seeded, report, result)
        assert golden(report, result) == json.loads(
            (CORPUS / seeded[2]["golden"]).read_text()
        )
        return report

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, seeded) for seeded in seeds]
        assert all(f.result(timeout=60)["balanced"] for f in futures)


@pytest.mark.parametrize("name", ["wo-composite", "td-mixed"])
def test_concurrent_reprocess_replay_then_actual_processing_preserves_original(
    corpus_db, name
):
    original = corpus_db.seed(name)
    corpus_db.repository.claim_processing(original[0], [original[2]["input_sha256"]])
    original_report, original_result = corpus_db.run(original)
    snapshot = corpus_db.snapshot(original[0])
    barrier = Barrier(2)
    candidates = ["corpus-" + uuid4().hex for _ in range(2)]

    def request(identifier):
        barrier.wait(timeout=15)
        return PostgresQueryRepository(corpus_db.database).request_reprocessing(
            original[0],
            identifier,
            "synthetic",
            "same-corpus-request",
            PIPELINE_VERSION,
            RULE_CATALOG["version"],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, candidates))
    assert len({r["execution_id"] for r in results}) == 1
    assert {r["idempotent_replay"] for r in results} == {True, False}
    retry = results[0]["execution_id"]
    corpus_db.ids.append(retry)
    seeded = corpus_db.attach(retry, name)
    report, result = corpus_db.run(seeded)
    assert golden(report, result) == golden(original_report, original_result)
    corpus_db.reconcile(seeded, report, result)
    assert corpus_db.snapshot(original[0]) == snapshot
    assert corpus_db.snapshot(retry) == snapshot


def test_generated_batches_run_concurrently_with_complete_persistence(
    corpus_db, tmp_path
):
    barrier = Barrier(2)
    seeds = []
    for source, content in (
        ("WO Status", workorder(rows=120, tail=8)[0]),
        ("Total Decision", decision(rows=160)),
    ):
        path = tmp_path / ("wo.xlsx" if source == "WO Status" else "td.xlsx")
        path.write_bytes(content)
        case = {"source": source, "input": str(path), "input_sha256": digest(content)}
        seeds.append(corpus_db.seed(case))

    def attempt(seeded):
        barrier.wait(timeout=15)
        assert (
            corpus_db.repository.claim_processing(
                seeded[0], [seeded[2]["input_sha256"]]
            )
            is None
        )
        report, result = corpus_db.run(seeded)
        corpus_db.reconcile(seeded, report, result)
        assert sum(s["normalized"] for s in report["sheets"]) == (
            300 if seeded[2]["source"] == "WO Status" else 160
        )
        assert sum(s["rejected"] for s in report["sheets"]) == (
            6 if seeded[2]["source"] == "WO Status" else 0
        )
        return report["balanced"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, seeded) for seeded in seeds]
        assert all(f.result(timeout=60) for f in futures)


@pytest.mark.parametrize("name", ["wo-nfp", "td-clean"])
@pytest.mark.parametrize(
    "variable,code",
    [
        ("INGESTION_MAX_ROWS", "workbook_row_limit"),
        ("INGESTION_MAX_MEMORY_BYTES", "workbook_memory_limit"),
    ],
)
def test_capacity_rejection_via_http_leaves_no_results_or_claim_and_allows_retry(
    corpus_db,
    tmp_path,
    monkeypatch,
    name,
    variable,
    code,
):
    org = corpus_db.organization()
    with psycopg.connect(corpus_db.database) as conn:
        user = conn.execute(
            "INSERT INTO synergia.identity_users "
            "(status, display_name) VALUES ('active', 'Synthetic corpus') "
            "RETURNING id"
        ).fetchone()[0]
    corpus_db.users.append(user)
    # Authentication is synthetic here; HTTP import, storage and DB are real.
    actor = ActorContext(
        user, None, uuid4(), {"import.create": frozenset({org})}, uuid4()
    )
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_actor_context] = lambda: actor
    app.dependency_overrides[get_repository] = lambda: corpus_db.repository
    case = next(c for c in CASES if c["id"] == name)
    content = (CORPUS / case["input"]).read_bytes()
    monkeypatch.setenv("IMPORT_STORAGE_DIR", str(tmp_path))
    # Use the source-specific limit so inherited local configuration cannot win.
    key = variable + (
        "_WO_STATUS" if case["source"] == "WO Status" else "_TOTAL_DECISION"
    )
    monkeypatch.setenv(key, "1")
    try:
        with TestClient(app) as client:
            response = client.post(
                "/imports",
                data={"source": case["source"]},
                files={
                    "file": (
                        "synthetic.xlsx",
                        content,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
            payload = response.json()
            identifier = payload["error"]["details"]["execution_id"]
            corpus_db.ids.append(identifier)
            assert response.status_code == 413
            assert payload["error"]["code"] == code
            assert corpus_db.repository.get(identifier)["status"] == "failed"
            with psycopg.connect(corpus_db.database) as conn:
                for table in (
                    "imported_records",
                    "normalized_records",
                    "workorders",
                    "execution_idempotency",
                    "source_files",
                ):
                    assert (
                        conn.execute(
                            f"SELECT count(*) FROM synergia.{table} "
                            "WHERE execution_id = %s",
                            (identifier,),
                        ).fetchone()[0]
                        == 0
                    )
            assert not [p for p in (tmp_path / "accepted").rglob("*") if p.is_file()]
            assert not list(tmp_path.rglob("*.json"))
            monkeypatch.delenv(key)
            retry = client.post(
                "/imports",
                data={"source": case["source"]},
                files={
                    "file": (
                        "synthetic.xlsx",
                        content,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )
            corpus_db.ids.append(retry.json()["execution_id"])
            assert retry.status_code == 201
            assert retry.json()["status"] == "completed"
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
