DROP TRIGGER IF EXISTS report_events_project_notification ON synergia.report_events;
DROP TRIGGER IF EXISTS audit_events_project_notification ON synergia.audit_events;
DROP FUNCTION IF EXISTS synergia.project_report_notification();
DROP FUNCTION IF EXISTS synergia.project_execution_notification();
DROP FUNCTION IF EXISTS synergia.enqueue_internal_notification(uuid, uuid, text, text, jsonb, text, text, bigint, timestamptz, uuid);
DROP FUNCTION IF EXISTS synergia.user_has_effective_permission(uuid, text, uuid);
DROP TRIGGER IF EXISTS notification_events_immutable ON synergia.notification_events;
DROP TRIGGER IF EXISTS notification_occurrences_immutable ON synergia.notification_occurrences;
DROP FUNCTION IF EXISTS synergia.prevent_notification_audit_mutation();
DROP FUNCTION IF EXISTS synergia.restrict_notification_occurrence_mutation();
DROP TABLE IF EXISTS synergia.notification_events;
DROP TABLE IF EXISTS synergia.notification_occurrences;
DROP TABLE IF EXISTS synergia.notifications;
DROP TABLE IF EXISTS synergia.notification_templates;
DROP TABLE IF EXISTS synergia.notification_template_versions;

DELETE FROM synergia.user_permission_assignments
WHERE permission_id IN (
    SELECT id FROM synergia.permissions WHERE normalized_key = 'notification.read'
);
DELETE FROM synergia.role_permissions
WHERE permission_id IN (
    SELECT id FROM synergia.permissions WHERE normalized_key = 'notification.read'
);
ALTER TABLE synergia.permissions DISABLE TRIGGER trg_permissions_no_delete;
DELETE FROM synergia.permissions WHERE normalized_key = 'notification.read';
ALTER TABLE synergia.permissions ENABLE TRIGGER trg_permissions_no_delete;
DELETE FROM synergia.permission_catalog_versions WHERE version = '1.2.0';
UPDATE synergia.permission_catalog_versions SET is_active = true WHERE version = '1.1.0';
