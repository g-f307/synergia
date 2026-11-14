-- Preserve catalog and historical assignments; revoke effective access.
UPDATE synergia.role_permissions SET revoked_at = now()
WHERE revoked_at IS NULL AND permission_id IN (
    SELECT id FROM synergia.permissions
    WHERE normalized_key IN ('ai.assistance.read', 'ai.assistance.generate')
);
UPDATE synergia.permissions
SET is_active = false, deactivated_at = now(), updated_at = now()
WHERE normalized_key IN ('ai.assistance.read', 'ai.assistance.generate');
UPDATE synergia.permission_catalog_versions SET is_active = false WHERE version = '1.6.0';
UPDATE synergia.permission_catalog_versions SET is_active = true WHERE version = '1.5.0';
