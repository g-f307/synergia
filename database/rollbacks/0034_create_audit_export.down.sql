-- Manual, transactional feature rollback. Preserve all export audit evidence.
-- Do not run against an active 0.10 API; return to the previous application first.
DROP VIEW synergia.audit_event_catalog;

UPDATE synergia.permissions
SET is_active = false, deactivated_at = now(), updated_at = now()
WHERE normalized_key = 'audit.export';

UPDATE synergia.permission_catalog_versions
SET is_active = false WHERE version = '1.4.0';
UPDATE synergia.permission_catalog_versions
SET is_active = true WHERE version = '1.3.0';

-- audit_export_events and catalog 1.4.0 remain for immutable history.
-- Dropping their referenced identities requires a separate preservation plan.
