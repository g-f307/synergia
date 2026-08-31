CREATE TABLE synergia.iam_organizations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_code text NOT NULL
        CHECK (
            organization_code = lower(btrim(organization_code))
            AND organization_code <> ''
        ),
    display_name text NOT NULL CHECK (btrim(display_name) <> ''),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deactivated_at timestamptz,
    UNIQUE (organization_code),
    CHECK (
        (is_active AND deactivated_at IS NULL)
        OR (NOT is_active AND deactivated_at IS NOT NULL)
    )
);

CREATE TABLE synergia.identity_groups (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_name text NOT NULL CHECK (btrim(group_name) <> ''),
    normalized_name text GENERATED ALWAYS AS (lower(btrim(group_name))) STORED,
    external_reference text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deactivated_at timestamptz,
    UNIQUE (normalized_name),
    CHECK (
        (is_active AND deactivated_at IS NULL)
        OR (NOT is_active AND deactivated_at IS NOT NULL)
    )
);

CREATE TABLE synergia.roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_key text NOT NULL CHECK (btrim(role_key) <> ''),
    normalized_key text GENERATED ALWAYS AS (lower(btrim(role_key))) STORED,
    description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deactivated_at timestamptz,
    UNIQUE (normalized_key),
    CHECK (
        (is_active AND deactivated_at IS NULL)
        OR (NOT is_active AND deactivated_at IS NOT NULL)
    )
);

CREATE TABLE synergia.permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    permission_key text NOT NULL CHECK (btrim(permission_key) <> ''),
    normalized_key text
        GENERATED ALWAYS AS (lower(btrim(permission_key))) STORED,
    resource_type text NOT NULL CHECK (btrim(resource_type) <> ''),
    description text,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deactivated_at timestamptz,
    UNIQUE (normalized_key),
    CHECK (
        normalized_key ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'
    ),
    CHECK (
        (is_active AND deactivated_at IS NULL)
        OR (NOT is_active AND deactivated_at IS NOT NULL)
    )
);

CREATE TABLE synergia.user_group_memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    group_id uuid NOT NULL REFERENCES synergia.identity_groups(id),
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

CREATE TABLE synergia.user_role_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    role_id uuid NOT NULL REFERENCES synergia.roles(id),
    organization_id uuid REFERENCES synergia.iam_organizations(id),
    granted_by_user_id uuid REFERENCES synergia.identity_users(id),
    granted_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    revocation_reason text,
    CHECK (expires_at IS NULL OR expires_at > granted_at),
    CHECK (revoked_at IS NULL OR revoked_at >= granted_at),
    CHECK (
        (revoked_at IS NULL AND revocation_reason IS NULL)
        OR (revoked_at IS NOT NULL AND btrim(revocation_reason) <> '')
    )
);

CREATE TABLE synergia.role_permissions (
    role_id uuid NOT NULL REFERENCES synergia.roles(id),
    permission_id uuid NOT NULL REFERENCES synergia.permissions(id),
    granted_by_user_id uuid REFERENCES synergia.identity_users(id),
    granted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (role_id, permission_id)
);

CREATE INDEX idx_iam_organizations_active
    ON synergia.iam_organizations (organization_code)
    WHERE is_active;

CREATE INDEX idx_identity_groups_active
    ON synergia.identity_groups (normalized_name)
    WHERE is_active;

CREATE INDEX idx_user_group_memberships_group
    ON synergia.user_group_memberships (group_id, user_id)
    WHERE revoked_at IS NULL;

CREATE UNIQUE INDEX uq_user_group_memberships_active
    ON synergia.user_group_memberships (user_id, group_id)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_user_role_assignments_user
    ON synergia.user_role_assignments (user_id, organization_id, role_id)
    WHERE revoked_at IS NULL;

CREATE INDEX idx_user_role_assignments_role
    ON synergia.user_role_assignments (role_id, organization_id, user_id)
    WHERE revoked_at IS NULL;

CREATE UNIQUE INDEX uq_user_role_assignments_global_active
    ON synergia.user_role_assignments (user_id, role_id)
    WHERE organization_id IS NULL AND revoked_at IS NULL;

CREATE UNIQUE INDEX uq_user_role_assignments_scoped_active
    ON synergia.user_role_assignments (user_id, role_id, organization_id)
    WHERE organization_id IS NOT NULL AND revoked_at IS NULL;

CREATE INDEX idx_role_permissions_permission
    ON synergia.role_permissions (permission_id, role_id);

COMMENT ON TABLE synergia.iam_organizations IS
    'Catalogo IAM estavel; codigos operacionais devem ser mapeados futuramente';

COMMENT ON TABLE synergia.user_role_assignments IS
    'Concessoes globais quando organization_id e nulo ou restritas a organizacao';

COMMENT ON COLUMN synergia.permissions.permission_key IS
    'Acao estavel no formato recurso.acao, autorizada pelo backend';
