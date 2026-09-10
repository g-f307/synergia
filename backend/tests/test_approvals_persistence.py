from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest

from app.approvals import ApprovalRepository
from app.authorization import ActorContext
from app.errors import ApiError

pytestmark = pytest.mark.integration


def _actor(user_id, session_id, org_id, *permissions):
    return ActorContext(
        user_id=user_id,
        session_id=session_id,
        token_id=uuid4(),
        permissions={key: frozenset({org_id}) for key in permissions},
        correlation_id=uuid4(),
    )


def _user(connection, name, role, org_id):
    user_id, session_id = uuid4(), uuid4()
    connection.execute(
        """
        INSERT INTO synergia.identity_users (id, status, display_name)
        VALUES (%s, 'active', %s)
        """,
        (user_id, name),
    )
    connection.execute(
        """
        INSERT INTO synergia.identity_sessions (
            id, user_id, status, authenticated_at, last_seen_at,
            idle_expires_at, absolute_expires_at, authentication_method
        ) VALUES (%s, %s, 'active', now(), now(), now() + interval '8 hours',
                  now() + interval '24 hours', 'synthetic')
        """,
        (session_id, user_id),
    )
    connection.execute(
        """
        INSERT INTO synergia.user_role_assignments (user_id, role_id, organization_id)
        SELECT %s, id, %s FROM synergia.roles WHERE normalized_key = %s
        """,
        (user_id, org_id, role),
    )
    return user_id, session_id


def _pending(connection, org_id, requester_id):
    execution_id = f"approval-{uuid4()}"
    connection.execute(
        """
        INSERT INTO synergia.executions (
            id, status, organization_id, initiated_by_user_id,
            state_changed_by_type, state_changed_by, state_change_reason
        ) VALUES (%s, 'completed', %s, %s, 'system', 'approval-test', 'completed')
        """,
        (execution_id, org_id, requester_id),
    )
    source_id = connection.execute(
        """
        INSERT INTO synergia.source_files (
            execution_id, file_name, content_hash, media_type, size_bytes
        ) VALUES (%s, %s, %s, 'text/csv', 1) RETURNING id
        """,
        (execution_id, f"{execution_id}.csv", uuid4().hex + uuid4().hex),
    ).fetchone()[0]
    workorder_id = connection.execute(
        """
        INSERT INTO synergia.workorders (
            workorder_number, execution_id, source_file_id, processing_status
        ) VALUES (%s, %s, %s, 'consolidated') RETURNING id
        """,
        (f"WO-{uuid4().hex[:12]}", execution_id, source_id),
    ).fetchone()[0]
    return connection.execute(
        """
        INSERT INTO synergia.pending_items (
            workorder_id, execution_id, source_file_id, category, reason
        ) VALUES (%s, %s, %s, 'oqc_hold', 'Synthetic review') RETURNING id
        """,
        (workorder_id, execution_id, source_id),
    ).fetchone()[0]


def test_full_flow_segregation_version_scope_history_and_notifications() -> None:
    database_url = os.environ["DATABASE_URL"]
    repository = ApprovalRepository(database_url)
    org_id, other_org_id = uuid4(), uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.iam_organizations (
                id, organization_code, display_name
            ) VALUES
                (%s, %s, 'Approval Org'),
                (%s, %s, 'Other Approval Org')
            """,
            (
                org_id,
                f"approval-{org_id.hex[:10]}",
                other_org_id,
                f"other-{other_org_id.hex[:10]}",
            ),
        )
        requester_id, requester_session = _user(
            connection, "Approval Requester", "operador", org_id
        )
        manager_id, manager_session = _user(
            connection, "Approval Manager", "gestor", org_id
        )
        pending_id = _pending(connection, org_id, requester_id)

    requester = _actor(
        requester_id, requester_session, org_id, "approval.read", "approval.submit"
    )
    manager = _actor(
        manager_id,
        manager_session,
        org_id,
        "approval.read",
        "approval.submit",
        "approval.assign",
        "approval.decide",
    )
    outside = _actor(uuid4(), uuid4(), other_org_id, "approval.read")

    created = repository.create(pending_id, "Needs human verification", requester)
    assert created["state"] == "submitted"
    assert repository.get_for_pending(pending_id, outside) is None
    assigned = repository.assign(
        created["id"], manager_id, created["version"], "Taking review", manager
    )
    assert assigned["state"] == "in_review"
    with pytest.raises(ApiError) as stale:
        repository.assign(
            created["id"], manager_id, created["version"], "Stale", manager
        )
    assert stale.value.status_code == 409
    with pytest.raises(ApiError) as missing_reason:
        repository.decide(
            assigned["id"], "approved", assigned["version"], "", True, manager
        )
    assert missing_reason.value.status_code == 422
    returned = repository.decide(
        assigned["id"],
        "returned",
        assigned["version"],
        "Correct source evidence",
        False,
        manager,
    )
    resubmitted = repository.resubmit(
        returned["id"], returned["version"], "Evidence corrected", requester
    )
    reassigned = repository.assign(
        resubmitted["id"],
        manager_id,
        resubmitted["version"],
        "Review corrected evidence",
        manager,
    )
    approved = repository.decide(
        reassigned["id"],
        "approved",
        reassigned["version"],
        "Evidence verified",
        True,
        manager,
    )
    assert approved["state"] == "approved"
    assert [event["event_type"] for event in approved["history"]] == [
        "submitted",
        "assigned",
        "returned",
        "resubmitted",
        "assigned",
        "approved",
    ]

    with psycopg.connect(database_url) as connection:
        stages = connection.execute(
            """
            SELECT sequence, state, assignee_user_id, closed_at IS NOT NULL
            FROM synergia.approval_stages
            WHERE request_id = %s
            ORDER BY sequence
            """,
            (approved["id"],),
        ).fetchall()
    assert stages == [
        (1, "returned", manager_id, True),
        (2, "completed", manager_id, True),
    ]

    with psycopg.connect(database_url) as connection:
        self_pending_id = _pending(connection, org_id, manager_id)
        rejected_pending_id = _pending(connection, org_id, requester_id)
    self_request = repository.create(self_pending_id, "Manager requested", manager)
    self_assigned = repository.assign(
        self_request["id"],
        manager_id,
        self_request["version"],
        "Self assignment",
        manager,
    )
    with pytest.raises(ApiError) as self_approval:
        repository.decide(
            self_assigned["id"],
            "approved",
            self_assigned["version"],
            "Must fail",
            True,
            manager,
        )
    assert self_approval.value.status_code == 422
    rejected_request = repository.create(
        rejected_pending_id, "Review second item", requester
    )
    rejected_assigned = repository.assign(
        rejected_request["id"],
        manager_id,
        rejected_request["version"],
        "Assigned",
        manager,
    )
    rejected = repository.decide(
        rejected_assigned["id"],
        "rejected",
        rejected_assigned["version"],
        "Evidence is invalid",
        False,
        manager,
    )
    assert rejected["state"] == "rejected"
    with psycopg.connect(database_url) as connection:
        notification_count = connection.execute(
            """
            SELECT count(*) FROM synergia.notifications
            WHERE notification_type LIKE 'approval.%'
            """
        ).fetchone()[0]
        assert notification_count > 0
        audit_payloads = connection.execute(
            """
            SELECT payload::text FROM synergia.identity_access_events
            WHERE entity_type = 'approval_request'
            """
        ).fetchall()
        assert all("Evidence verified" not in payload for (payload,) in audit_payloads)
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE synergia.approval_events
                SET justification = 'tampered' WHERE request_id = %s
                """,
                (approved["id"],),
            )


def test_assignee_must_belong_to_policy_review_role() -> None:
    database_url = os.environ["DATABASE_URL"]
    repository = ApprovalRepository(database_url)
    org_id = uuid4()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO synergia.iam_organizations (
                id, organization_code, display_name
            ) VALUES (%s, %s, 'Approval Eligibility Org')
            """,
            (org_id, f"approval-role-{org_id.hex[:10]}"),
        )
        requester_id, requester_session = _user(
            connection, "Eligibility Requester", "operador", org_id
        )
        direct_id, _ = _user(
            connection, "Direct Permission User", "consulta", org_id
        )
        connection.execute(
            """
            INSERT INTO synergia.user_permission_assignments (
                user_id, permission_id, organization_id
            )
            SELECT %s, id, %s FROM synergia.permissions
            WHERE normalized_key = 'approval.decide'
            """,
            (direct_id, org_id),
        )
        pending_id = _pending(connection, org_id, requester_id)
    requester = _actor(
        requester_id, requester_session, org_id, "approval.read", "approval.submit"
    )
    assigner = _actor(
        requester_id, requester_session, org_id, "approval.assign"
    )
    created = repository.create(pending_id, "Needs eligible reviewer", requester)
    with pytest.raises(ApiError) as error:
        repository.assign(
            created["id"],
            direct_id,
            created["version"],
            "Direct grant only",
            assigner,
        )
    assert error.value.status_code == 422
    assert error.value.code == "assignee_not_eligible"


def test_published_policy_version_is_immutable() -> None:
    database_url = os.environ["DATABASE_URL"]
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                UPDATE synergia.approval_policies
                SET require_distinct_approver = false
                WHERE policy_key = 'pending.standard' AND version = 1
                """
            )
    with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
        with psycopg.connect(database_url) as connection:
            connection.execute(
                """
                DELETE FROM synergia.approval_policies
                WHERE policy_key = 'pending.standard' AND version = 1
                """
            )
