-- Explicit export permission; administration alone does not grant export.
UPDATE synergia.permission_catalog_versions SET is_active = false WHERE is_active;
INSERT INTO synergia.permission_catalog_versions (version, description, is_active)
VALUES ('1.4.0', 'Exportacao segura e segregada de auditoria', true);

INSERT INTO synergia.permissions
    (permission_key, resource_type, description, catalog_version, is_reserved)
VALUES ('audit.export', 'audit', 'Exportar auditoria sanitizada', '1.4.0', true);

INSERT INTO synergia.role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM synergia.roles r
JOIN synergia.permissions p ON p.normalized_key = 'audit.export'
WHERE r.normalized_key IN ('gestor', 'analista')
ON CONFLICT (role_id, permission_id) WHERE revoked_at IS NULL DO NOTHING;

CREATE TABLE synergia.audit_export_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    export_id uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('requested', 'succeeded', 'failed')),
    actor_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    actor_session_id uuid NOT NULL REFERENCES synergia.identity_sessions(id),
    organization_id uuid REFERENCES synergia.iam_organizations(id),
    correlation_id uuid NOT NULL,
    export_format text NOT NULL CHECK (export_format IN ('json', 'csv')),
    filters jsonb NOT NULL CHECK (jsonb_typeof(filters) = 'object'),
    event_count integer CHECK (event_count BETWEEN 0 AND 10000),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (export_id, action)
);
CREATE UNIQUE INDEX audit_export_events_one_result
    ON synergia.audit_export_events (export_id) WHERE action <> 'requested';
CREATE INDEX audit_export_events_scope_time
    ON synergia.audit_export_events (organization_id, occurred_at, id);
CREATE TRIGGER audit_export_events_immutable
BEFORE UPDATE OR DELETE ON synergia.audit_export_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_data_operation_event_mutation();

-- No log messages, arbitrary payloads, filenames, addresses or provider responses.
-- NULL organization denotes global events, never a wildcard.
CREATE VIEW synergia.audit_event_catalog AS
SELECT 'execution:' || a.id AS id, a.occurred_at, e.organization_id,
       CASE WHEN COALESCE(a.payload->>'actor_identifier', '') ~
           '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
           THEN (a.payload->>'actor_identifier')::uuid END AS actor_id,
       CASE WHEN a.payload->>'actor_type' = 'user' THEN 'user'
            WHEN a.payload->>'actor_type' IN ('technical', 'system') THEN 'system'
            ELSE 'unknown' END AS actor_type,
       a.event_type AS action, a.entity_type AS resource_type,
       a.entity_id AS resource_id,
       CASE WHEN a.event_type ~ '(failed|rejected)$' THEN 'failure'
            WHEN a.event_type IN ('execution_started', 'execution_transitioned')
                THEN 'started' ELSE 'success' END AS outcome,
       a.correlation_id,
       jsonb_build_object('from_state', a.payload->'from_state',
           'to_state', a.payload->'to_state',
           'state_version', a.payload->'state_version',
           'version', a.payload->'version') AS metadata,
       'audit_events'::text AS origin
FROM synergia.audit_events a
JOIN synergia.executions e ON e.id = a.execution_id
UNION ALL
SELECT 'identity:' || a.id, a.occurred_at, a.organization_id,
       a.actor_user_id, CASE WHEN a.actor_user_id IS NULL
           THEN 'unknown' ELSE 'user' END,
       a.event_key, a.entity_type, a.entity_id,
       CASE WHEN a.event_key ~ '(failed|denied|blocked|replay_detected|reused|rate_limited)$'
           THEN 'failure' ELSE 'success' END,
       a.correlation_id, '{}'::jsonb, 'identity_access_events'
FROM synergia.identity_access_events a
UNION ALL
SELECT 'report:' || a.id, a.occurred_at, r.organization_id,
       a.actor_user_id, CASE WHEN a.actor_user_id IS NULL
           THEN 'system' ELSE 'user' END,
       a.event_type, 'report_version', a.report_version_id::text,
       CASE WHEN a.event_type = 'report.generation_failed' THEN 'failure'
            WHEN a.event_type = 'report.generation_started' THEN 'started'
            ELSE 'success' END,
       a.correlation_id,
       jsonb_build_object('format', a.payload->'format', 'version', r.version),
       'report_events'
FROM synergia.report_events a
JOIN synergia.report_versions r ON r.id = a.report_version_id
UNION ALL
SELECT 'approval:' || a.id, a.occurred_at, a.organization_id,
       a.actor_user_id, 'user', 'approval.' || a.event_type,
       'approval_request', a.request_id::text, 'success', a.correlation_id,
       jsonb_build_object('from_state', a.from_state, 'to_state', a.to_state,
           'version', a.request_version, 'consent', a.consent),
       'approval_events'
FROM synergia.approval_events a
UNION ALL
SELECT 'notification:' || a.id, a.occurred_at, n.organization_id,
       a.actor_user_id, CASE WHEN a.actor_user_id IS NULL
           THEN 'system' ELSE 'user' END,
       a.event_type, 'notification', COALESCE(a.notification_id::text, a.id::text),
       CASE WHEN a.event_type = 'notification.delivery_failed'
           THEN 'failure' ELSE 'success' END,
       a.correlation_id, '{}'::jsonb, 'notification_events'
FROM synergia.notification_events a
LEFT JOIN synergia.notifications n ON n.id = a.notification_id
UNION ALL
SELECT 'template:' || a.id, a.occurred_at, NULL::uuid,
       a.actor_user_id, CASE WHEN a.actor_user_id IS NULL
           THEN 'system' ELSE 'user' END,
       a.event_type, 'notification_template', a.revision_id::text,
       'success', a.correlation_id, '{}'::jsonb, 'notification_template_events'
FROM synergia.notification_template_events a
UNION ALL
SELECT 'data_operation:' || a.id, a.occurred_at, NULL::uuid, NULL::uuid,
       'system', 'data.' || a.operation, 'dataset', a.dataset,
       CASE WHEN a.outcome IN ('failed', 'refused') THEN 'failure'
            WHEN a.outcome = 'started' THEN 'started' ELSE 'success' END,
       a.correlation_id, jsonb_build_object('record_count', a.record_count,
           'artifact_count', a.artifact_count, 'duration_ms', a.duration_ms),
       'data_operation_events'
FROM synergia.data_operation_events a
UNION ALL
SELECT 'policy:' || a.id, a.changed_at, NULL::uuid, NULL::uuid, 'system',
       'approval.policy_activation', 'approval_policy', a.policy_key,
       'success', NULL::uuid,
       jsonb_build_object('version', a.policy_version, 'is_active', a.is_active),
       'approval_policy_activation_events'
FROM synergia.approval_policy_activation_events a
UNION ALL
SELECT 'email_attempt:' || a.id, a.occurred_at, n.organization_id,
       NULL::uuid, 'system', 'email.' || a.outcome,
       'email_delivery', a.delivery_id::text,
       CASE WHEN a.outcome IN ('failed', 'retry') THEN 'failure'
            WHEN a.outcome = 'started' THEN 'started' ELSE 'success' END,
       a.correlation_id, jsonb_build_object('attempt_number', a.attempt_number),
       'email_delivery_attempts'
FROM synergia.email_delivery_attempts a
JOIN synergia.email_deliveries d ON d.id = a.delivery_id
JOIN synergia.notifications n ON n.id = d.notification_id
UNION ALL
SELECT 'email_reconciliation:' || a.id, a.occurred_at, n.organization_id,
       NULL::uuid, 'system', 'email.reconciled', 'email_delivery',
       a.delivery_id::text, 'success', a.correlation_id,
       jsonb_build_object('attempt_number', a.attempt_number,
           'to_state', a.resulting_state), 'email_delivery_reconciliations'
FROM synergia.email_delivery_reconciliations a
JOIN synergia.email_deliveries d ON d.id = a.delivery_id
JOIN synergia.notifications n ON n.id = d.notification_id
UNION ALL
SELECT 'audit_export:' || a.id, a.occurred_at, a.organization_id,
       a.actor_user_id, 'user', 'audit.export_' || a.action,
       'audit_export', a.export_id::text,
       CASE WHEN a.action = 'failed' THEN 'failure'
            WHEN a.action = 'requested' THEN 'started' ELSE 'success' END,
       a.correlation_id,
       jsonb_build_object('format', a.export_format, 'event_count', a.event_count),
       'audit_export_events'
FROM synergia.audit_export_events a;

CREATE INDEX audit_events_time_scope ON synergia.audit_events (occurred_at, id);
CREATE INDEX identity_access_events_scope_time
    ON synergia.identity_access_events (organization_id, occurred_at, id);
