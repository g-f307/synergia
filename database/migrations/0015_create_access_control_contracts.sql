CREATE TABLE synergia.permission_catalog_versions (
    version text PRIMARY KEY CHECK (btrim(version) <> ''),
    description text NOT NULL CHECK (btrim(description) <> ''),
    is_active boolean NOT NULL DEFAULT false,
    published_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_permission_catalog_active
    ON synergia.permission_catalog_versions (is_active)
    WHERE is_active;

INSERT INTO synergia.permission_catalog_versions (version, description, is_active)
VALUES ('1.0.0', 'Matriz inicial de acesso da Etapa 2', true);

ALTER TABLE synergia.permissions
    DROP CONSTRAINT permissions_normalized_key_check;

ALTER TABLE synergia.permissions
    ADD CHECK (
        normalized_key ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'
    ),
    ADD COLUMN catalog_version text NOT NULL DEFAULT '1.0.0'
        REFERENCES synergia.permission_catalog_versions(version),
    ADD COLUMN is_reserved boolean NOT NULL DEFAULT true,
    ADD COLUMN preexisting_in_0015 boolean NOT NULL DEFAULT false;

UPDATE synergia.permissions SET preexisting_in_0015 = true;

ALTER TABLE synergia.identity_groups
    ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0);

ALTER TABLE synergia.roles
    ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0);

CREATE OR REPLACE FUNCTION synergia.touch_versioned_access_entity()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    NEW.version = OLD.version + 1;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_identity_groups_touch
BEFORE UPDATE ON synergia.identity_groups
FOR EACH ROW EXECUTE FUNCTION synergia.touch_versioned_access_entity();

CREATE TRIGGER trg_roles_touch
BEFORE UPDATE ON synergia.roles
FOR EACH ROW EXECUTE FUNCTION synergia.touch_versioned_access_entity();

ALTER TABLE synergia.role_permissions
    DROP CONSTRAINT role_permissions_pkey,
    ADD COLUMN id uuid DEFAULT gen_random_uuid(),
    ADD COLUMN revoked_at timestamptz,
    ADD COLUMN revocation_reason text,
    ADD COLUMN preexisting_in_0015 boolean NOT NULL DEFAULT false;

UPDATE synergia.role_permissions SET preexisting_in_0015 = true;

ALTER TABLE synergia.role_permissions
    ALTER COLUMN id SET NOT NULL,
    ADD PRIMARY KEY (id),
    ADD CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    ADD CHECK (
        (revoked_at IS NULL AND revocation_reason IS NULL)
        OR (revoked_at IS NOT NULL AND btrim(revocation_reason) <> '')
    );

CREATE UNIQUE INDEX uq_role_permissions_active
    ON synergia.role_permissions (role_id, permission_id)
    WHERE revoked_at IS NULL;

CREATE TABLE synergia.group_role_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id uuid NOT NULL REFERENCES synergia.identity_groups(id),
    role_id uuid NOT NULL REFERENCES synergia.roles(id),
    organization_id uuid REFERENCES synergia.iam_organizations(id),
    granted_by_user_id uuid REFERENCES synergia.identity_users(id),
    granted_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    revocation_reason text,
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    CHECK (
        (revoked_at IS NULL AND revocation_reason IS NULL)
        OR (revoked_at IS NOT NULL AND btrim(revocation_reason) <> '')
    )
);

CREATE UNIQUE INDEX uq_group_roles_global_active
    ON synergia.group_role_assignments (group_id, role_id)
    WHERE organization_id IS NULL AND revoked_at IS NULL;

CREATE UNIQUE INDEX uq_group_roles_scoped_active
    ON synergia.group_role_assignments (group_id, role_id, organization_id)
    WHERE organization_id IS NOT NULL AND revoked_at IS NULL;

CREATE INDEX idx_group_roles_group
    ON synergia.group_role_assignments (group_id, organization_id, role_id)
    WHERE revoked_at IS NULL;

CREATE TABLE synergia.user_permission_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    permission_id uuid NOT NULL REFERENCES synergia.permissions(id),
    organization_id uuid REFERENCES synergia.iam_organizations(id),
    granted_by_user_id uuid REFERENCES synergia.identity_users(id),
    granted_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    revocation_reason text,
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    CHECK (
        (revoked_at IS NULL AND revocation_reason IS NULL)
        OR (revoked_at IS NOT NULL AND btrim(revocation_reason) <> '')
    )
);

CREATE UNIQUE INDEX uq_user_permissions_global_active
    ON synergia.user_permission_assignments (user_id, permission_id)
    WHERE organization_id IS NULL AND revoked_at IS NULL;

CREATE UNIQUE INDEX uq_user_permissions_scoped_active
    ON synergia.user_permission_assignments (
        user_id, permission_id, organization_id
    ) WHERE organization_id IS NOT NULL AND revoked_at IS NULL;

CREATE INDEX idx_user_permissions_user
    ON synergia.user_permission_assignments (
        user_id, organization_id, permission_id
    ) WHERE revoked_at IS NULL;

INSERT INTO synergia.roles (role_key, description)
VALUES
    ('admin', 'Administracao de identidade e acesso'),
    ('gestor', 'Supervisao operacional'),
    ('analista', 'Investigacao e auditoria operacional'),
    ('operador', 'Importacao e acompanhamento operacional'),
    ('consulta', 'Consulta de indicadores e resultados')
ON CONFLICT (normalized_key) DO NOTHING;

INSERT INTO synergia.permissions (
    permission_key, resource_type, description, catalog_version, is_reserved
)
VALUES
    ('dashboard.read', 'dashboard', 'Consultar indicadores', '1.0.0', true),
    ('execution.read', 'execution', 'Consultar execucoes', '1.0.0', true),
    ('business.read', 'business', 'Consultar entidades operacionais', '1.0.0', true),
    ('pending.read', 'pending', 'Consultar pendencias', '1.0.0', true),
    ('import.create', 'import', 'Iniciar importacao', '1.0.0', true),
    ('import.read', 'import', 'Acompanhar importacao', '1.0.0', true),
    ('artifact.read', 'artifact', 'Consultar artefatos', '1.0.0', true),
    ('execution.reprocess', 'execution', 'Solicitar reprocessamento', '1.0.0', true),
    ('audit.read', 'audit', 'Consultar auditoria', '1.0.0', true),
    ('artifact.export', 'artifact', 'Baixar evidencias', '1.0.0', true),
    ('report.export', 'report', 'Exportar relatorios', '1.0.0', true),
    ('access.admin', 'access', 'Administrar identidade e acesso', '1.0.0', true),
    ('session.revoke.any', 'session', 'Revogar sessoes de terceiros', '1.0.0', true),
    ('session.revoke.own', 'session', 'Revogar a propria sessao', '1.0.0', true)
ON CONFLICT (normalized_key) DO NOTHING;

INSERT INTO synergia.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM synergia.roles r
JOIN synergia.permissions p ON (
    (r.normalized_key = 'admin' AND p.normalized_key IN (
        'audit.read', 'access.admin', 'session.revoke.any', 'session.revoke.own'
    ))
    OR (r.normalized_key = 'gestor' AND p.normalized_key IN (
        'dashboard.read', 'execution.read', 'business.read', 'pending.read',
        'import.create', 'import.read', 'artifact.read', 'execution.reprocess',
        'audit.read', 'artifact.export', 'report.export', 'session.revoke.own'
    ))
    OR (r.normalized_key = 'analista' AND p.normalized_key IN (
        'dashboard.read', 'execution.read', 'business.read', 'pending.read',
        'import.read', 'artifact.read', 'audit.read', 'artifact.export',
        'report.export', 'session.revoke.own'
    ))
    OR (r.normalized_key = 'operador' AND p.normalized_key IN (
        'dashboard.read', 'execution.read', 'business.read', 'pending.read',
        'import.create', 'import.read', 'artifact.read', 'session.revoke.own'
    ))
    OR (r.normalized_key = 'consulta' AND p.normalized_key IN (
        'dashboard.read', 'execution.read', 'business.read', 'pending.read',
        'session.revoke.own'
    ))
)
ON CONFLICT (role_id, permission_id) WHERE revoked_at IS NULL DO NOTHING;

COMMENT ON TABLE synergia.permission_catalog_versions IS
    'Versoes publicadas do catalogo estavel de permissoes';

COMMENT ON TABLE synergia.group_role_assignments IS
    'Papeis herdados por integrantes ativos de um grupo';

COMMENT ON TABLE synergia.user_permission_assignments IS
    'Concessoes diretas excepcionais, distintas de papel e grupo';
