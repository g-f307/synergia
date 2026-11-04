-- Manual feature rollback: retain feedback, protocols and immutable history.
UPDATE synergia.permissions
SET is_active = false, deactivated_at = now(), updated_at = now()
WHERE normalized_key = 'feedback.triage';
UPDATE synergia.permission_catalog_versions SET is_active = false
WHERE version = '1.5.0';
UPDATE synergia.permission_catalog_versions SET is_active = true
WHERE version = '1.4.0';
-- No destructive downgrade of feedback or identity audit is supported.
