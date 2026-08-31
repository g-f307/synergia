CREATE TABLE synergia.identity_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('active', 'inactive', 'blocked', 'pending')),
    display_name text NOT NULL CHECK (btrim(display_name) <> ''),
    local_password_hash text
        CHECK (
            local_password_hash IS NULL
            OR local_password_hash ~ '^\$argon2id\$'
        ),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    deactivated_at timestamptz,
    last_login_at timestamptz,
    CHECK (
        (status = 'inactive' AND deactivated_at IS NOT NULL)
        OR (status <> 'inactive' AND deactivated_at IS NULL)
    ),
    CHECK (updated_at >= created_at),
    CHECK (last_login_at IS NULL OR last_login_at >= created_at)
);

CREATE TABLE synergia.user_external_identities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    provider_key text NOT NULL
        CHECK (provider_key = lower(btrim(provider_key)) AND provider_key <> ''),
    subject_identifier text NOT NULL CHECK (btrim(subject_identifier) <> ''),
    linked_at timestamptz NOT NULL DEFAULT now(),
    last_authenticated_at timestamptz,
    disabled_at timestamptz,
    provider_attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (provider_key, subject_identifier),
    UNIQUE (id, user_id),
    CHECK (
        last_authenticated_at IS NULL
        OR last_authenticated_at >= linked_at
    )
);

CREATE TABLE synergia.user_emails (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    email text NOT NULL CHECK (btrim(email) <> ''),
    normalized_email text GENERATED ALWAYS AS (lower(btrim(email))) STORED,
    is_primary boolean NOT NULL DEFAULT false,
    is_verified boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    verified_at timestamptz,
    disabled_at timestamptz,
    UNIQUE (normalized_email),
    UNIQUE (id, user_id),
    CHECK (position('@' IN normalized_email) > 1),
    CHECK (
        (is_verified AND verified_at IS NOT NULL)
        OR (NOT is_verified AND verified_at IS NULL)
    ),
    CHECK (verified_at IS NULL OR verified_at >= created_at)
);

CREATE UNIQUE INDEX uq_user_emails_primary_active
    ON synergia.user_emails (user_id)
    WHERE is_primary AND disabled_at IS NULL;

CREATE INDEX idx_identity_users_status
    ON synergia.identity_users (status);

CREATE INDEX idx_external_identities_user
    ON synergia.user_external_identities (user_id)
    WHERE disabled_at IS NULL;

CREATE INDEX idx_external_identities_login
    ON synergia.user_external_identities (provider_key, subject_identifier)
    WHERE disabled_at IS NULL;

CREATE INDEX idx_user_emails_user
    ON synergia.user_emails (user_id)
    WHERE disabled_at IS NULL;

CREATE INDEX idx_user_emails_login
    ON synergia.user_emails (normalized_email)
    WHERE disabled_at IS NULL;

COMMENT ON TABLE synergia.identity_users IS
    'Usuarios internos estaveis, independentes de email ou provedor externo';

COMMENT ON COLUMN synergia.identity_users.local_password_hash IS
    'Hash Argon2id opcional; senha em texto puro nunca e persistida';

COMMENT ON TABLE synergia.user_external_identities IS
    'Vinculos neutros entre usuario interno e sujeitos de provedores';

COMMENT ON COLUMN synergia.user_emails.normalized_email IS
    'Email normalizado com unicidade global case-insensitive para login';
