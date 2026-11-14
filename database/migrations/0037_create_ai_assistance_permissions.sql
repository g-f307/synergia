-- Explicit grants only; access administration does not imply business access.
UPDATE synergia.permission_catalog_versions SET is_active = false WHERE is_active;
INSERT INTO synergia.permission_catalog_versions (version, description, is_active)
VALUES ('1.6.0', 'Assistencia informativa de IA por execucao', true);

INSERT INTO synergia.permissions
    (permission_key, resource_type, description, catalog_version, is_reserved)
VALUES
    ('ai.assistance.read', 'execution', 'Ler assistencia informativa de IA', '1.6.0', true),
    ('ai.assistance.generate', 'execution', 'Solicitar assistencia informativa de IA', '1.6.0', true);

INSERT INTO synergia.role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM synergia.roles r
JOIN synergia.permissions p ON p.normalized_key IN
    ('ai.assistance.read', 'ai.assistance.generate')
WHERE r.normalized_key IN ('gestor', 'analista');
