DROP TRIGGER IF EXISTS report_events_immutable ON synergia.report_events;
DROP FUNCTION IF EXISTS synergia.prevent_report_event_mutation();
DROP TRIGGER IF EXISTS report_artifacts_immutable ON synergia.report_artifacts;
DROP FUNCTION IF EXISTS synergia.prevent_report_artifact_mutation();
DROP TRIGGER IF EXISTS report_versions_immutable ON synergia.report_versions;
DROP FUNCTION IF EXISTS synergia.prevent_report_history_mutation();
DROP TRIGGER IF EXISTS reports_immutable ON synergia.reports;
DROP FUNCTION IF EXISTS synergia.prevent_report_catalog_mutation();
DROP TABLE IF EXISTS synergia.report_events;
DROP TABLE IF EXISTS synergia.report_artifacts;
DROP TABLE IF EXISTS synergia.report_versions;
DROP TABLE IF EXISTS synergia.reports;
ALTER TABLE synergia.executions
    DROP CONSTRAINT IF EXISTS executions_id_organization_key;

DELETE FROM synergia.role_permissions
WHERE permission_id IN (
    SELECT id FROM synergia.permissions
    WHERE normalized_key IN ('report.generate', 'report.read')
);
ALTER TABLE synergia.permissions DISABLE TRIGGER trg_permissions_no_delete;
DELETE FROM synergia.permissions
WHERE normalized_key IN ('report.generate', 'report.read');
ALTER TABLE synergia.permissions ENABLE TRIGGER trg_permissions_no_delete;
DELETE FROM synergia.permission_catalog_versions WHERE version = '1.1.0';
UPDATE synergia.permission_catalog_versions SET is_active = true WHERE version = '1.0.0';
