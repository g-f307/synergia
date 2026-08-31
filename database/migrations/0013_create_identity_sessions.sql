CREATE TABLE synergia.identity_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked', 'expired')),
    authenticated_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    idle_expires_at timestamptz NOT NULL,
    absolute_expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    revocation_reason text,
    authentication_method text NOT NULL
        CHECK (btrim(authentication_method) <> ''),
    client_fingerprint_hash text
        CHECK (
            client_fingerprint_hash IS NULL
            OR client_fingerprint_hash ~ '^[0-9a-f]{64}$'
        ),
    created_ip_hash text
        CHECK (
            created_ip_hash IS NULL
            OR created_ip_hash ~ '^[0-9a-f]{64}$'
        ),
    CHECK (last_seen_at >= authenticated_at),
    CHECK (idle_expires_at > authenticated_at),
    CHECK (absolute_expires_at >= idle_expires_at),
    CHECK (
        (status = 'active' AND revoked_at IS NULL AND revocation_reason IS NULL)
        OR (
            status = 'revoked'
            AND revoked_at IS NOT NULL
            AND btrim(revocation_reason) <> ''
        )
        OR (status = 'expired' AND revoked_at IS NULL)
    )
);

CREATE TABLE synergia.session_refresh_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id uuid NOT NULL REFERENCES synergia.identity_sessions(id),
    family_id uuid NOT NULL,
    token_hash text NOT NULL UNIQUE
        CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'used', 'revoked', 'expired')),
    issued_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    revoked_at timestamptz,
    revocation_reason text,
    replaced_by_token_id uuid,
    UNIQUE (id, session_id),
    CHECK (expires_at > issued_at),
    CHECK (
        (status = 'active' AND used_at IS NULL AND revoked_at IS NULL)
        OR (status = 'used' AND used_at IS NOT NULL AND revoked_at IS NULL)
        OR (
            status = 'revoked'
            AND revoked_at IS NOT NULL
            AND btrim(revocation_reason) <> ''
        )
        OR (status = 'expired' AND used_at IS NULL AND revoked_at IS NULL)
    ),
    CHECK (used_at IS NULL OR used_at >= issued_at),
    CHECK (revoked_at IS NULL OR revoked_at >= issued_at),
    FOREIGN KEY (replaced_by_token_id, session_id)
        REFERENCES synergia.session_refresh_tokens(id, session_id)
);

CREATE TABLE synergia.identity_access_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL
        CHECK (
            event_key = lower(btrim(event_key))
            AND event_key ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'
        ),
    actor_user_id uuid REFERENCES synergia.identity_users(id),
    subject_user_id uuid REFERENCES synergia.identity_users(id),
    session_id uuid REFERENCES synergia.identity_sessions(id),
    organization_id uuid REFERENCES synergia.iam_organizations(id),
    entity_type text NOT NULL CHECK (btrim(entity_type) <> ''),
    entity_id text NOT NULL CHECK (btrim(entity_id) <> ''),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_identity_sessions_user_active
    ON synergia.identity_sessions (user_id, last_seen_at, id)
    WHERE status = 'active';

CREATE INDEX idx_identity_sessions_validation
    ON synergia.identity_sessions (id, absolute_expires_at, idle_expires_at)
    WHERE status = 'active';

CREATE INDEX idx_refresh_tokens_session
    ON synergia.session_refresh_tokens (session_id, family_id, issued_at);

CREATE INDEX idx_refresh_tokens_validation
    ON synergia.session_refresh_tokens (token_hash, expires_at)
    WHERE status = 'active';

CREATE INDEX idx_identity_events_subject
    ON synergia.identity_access_events (subject_user_id, occurred_at DESC);

CREATE INDEX idx_identity_events_entity
    ON synergia.identity_access_events (entity_type, entity_id, occurred_at DESC);

CREATE INDEX idx_identity_events_session
    ON synergia.identity_access_events (session_id, occurred_at DESC)
    WHERE session_id IS NOT NULL;

CREATE OR REPLACE FUNCTION synergia.touch_identity_user()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION synergia.validate_identity_session()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    current_user_status text;
    active_session_count integer;
BEGIN
    IF NEW.status <> 'active' THEN
        RETURN NEW;
    END IF;

    SELECT status INTO current_user_status
    FROM synergia.identity_users
    WHERE id = NEW.user_id
    FOR UPDATE;

    IF current_user_status IS NULL THEN
        RAISE EXCEPTION 'identity user does not exist'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF current_user_status <> 'active' THEN
        RAISE EXCEPTION 'inactive identity user cannot own an active session'
            USING ERRCODE = 'check_violation';
    END IF;

    IF TG_OP = 'INSERT' THEN
        SELECT count(*) INTO active_session_count
        FROM synergia.identity_sessions
        WHERE user_id = NEW.user_id AND status = 'active';

        IF active_session_count >= 3 THEN
            UPDATE synergia.identity_sessions
            SET status = 'revoked',
                revoked_at = now(),
                revocation_reason = 'concurrent_session_limit'
            WHERE id = (
                SELECT id
                FROM synergia.identity_sessions
                WHERE user_id = NEW.user_id AND status = 'active'
                ORDER BY last_seen_at, authenticated_at, id
                LIMIT 1
            );
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION synergia.audit_identity_user()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO synergia.identity_access_events (
        event_key, subject_user_id, entity_type, entity_id, payload
    ) VALUES (
        CASE
            WHEN TG_OP = 'INSERT' THEN 'user.created'
            WHEN NEW.status = 'inactive' AND OLD.status <> 'inactive'
                THEN 'user.deactivated'
            ELSE 'user.updated'
        END,
        NEW.id,
        'identity_user',
        NEW.id::text,
        jsonb_build_object(
            'status', NEW.status,
            'previous_status', CASE WHEN TG_OP = 'UPDATE' THEN OLD.status END,
            'updated_at', NEW.updated_at
        )
    );
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION synergia.after_identity_session_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE synergia.identity_users
        SET last_login_at = NEW.authenticated_at
        WHERE id = NEW.user_id;
    END IF;

    INSERT INTO synergia.identity_access_events (
        event_key, subject_user_id, session_id, entity_type, entity_id, payload
    ) VALUES (
        CASE
            WHEN TG_OP = 'INSERT' THEN 'session.created'
            WHEN NEW.status = 'revoked' AND OLD.status <> 'revoked'
                THEN 'session.revoked'
            ELSE 'session.updated'
        END,
        NEW.user_id,
        NEW.id,
        'identity_session',
        NEW.id::text,
        jsonb_build_object(
            'status', NEW.status,
            'authentication_method', NEW.authentication_method,
            'revocation_reason', NEW.revocation_reason
        )
    );
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION synergia.revoke_sessions_for_inactive_user()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status <> 'active' AND OLD.status = 'active' THEN
        UPDATE synergia.identity_sessions
        SET status = 'revoked',
            revoked_at = now(),
            revocation_reason = 'user_status_changed'
        WHERE user_id = NEW.id AND status = 'active';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION synergia.prevent_identity_hard_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'physical deletion is forbidden for identity and access data'
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE OR REPLACE FUNCTION synergia.prevent_identity_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'identity access events are append-only'
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER trg_identity_users_touch
BEFORE UPDATE ON synergia.identity_users
FOR EACH ROW EXECUTE FUNCTION synergia.touch_identity_user();

CREATE TRIGGER trg_identity_sessions_validate
BEFORE INSERT OR UPDATE OF user_id, status ON synergia.identity_sessions
FOR EACH ROW EXECUTE FUNCTION synergia.validate_identity_session();

CREATE TRIGGER trg_identity_users_audit
AFTER INSERT OR UPDATE ON synergia.identity_users
FOR EACH ROW EXECUTE FUNCTION synergia.audit_identity_user();

CREATE TRIGGER trg_identity_sessions_audit
AFTER INSERT OR UPDATE ON synergia.identity_sessions
FOR EACH ROW EXECUTE FUNCTION synergia.after_identity_session_change();

CREATE TRIGGER trg_identity_users_revoke_sessions
AFTER UPDATE OF status ON synergia.identity_users
FOR EACH ROW EXECUTE FUNCTION synergia.revoke_sessions_for_inactive_user();

CREATE TRIGGER trg_identity_events_append_only
BEFORE UPDATE OR DELETE ON synergia.identity_access_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_identity_event_mutation();

DO $$
DECLARE
    protected_table text;
BEGIN
    FOREACH protected_table IN ARRAY ARRAY[
        'identity_users',
        'user_external_identities',
        'user_emails',
        'iam_organizations',
        'identity_groups',
        'roles',
        'permissions',
        'identity_sessions',
        'session_refresh_tokens'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%I_no_delete '
            'BEFORE DELETE ON synergia.%I '
            'FOR EACH ROW EXECUTE FUNCTION synergia.prevent_identity_hard_delete()',
            protected_table,
            protected_table
        );
    END LOOP;
END;
$$;

COMMENT ON TABLE synergia.identity_sessions IS
    'Sessoes revogaveis; no maximo tres ativas por usuario';

COMMENT ON COLUMN synergia.session_refresh_tokens.token_hash IS
    'Hash SHA-256 do segredo aleatorio; refresh token puro nunca e persistido';

COMMENT ON TABLE synergia.identity_access_events IS
    'Historico append-only de identidade, sessao e autorizacao';
