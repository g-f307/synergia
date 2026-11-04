UPDATE synergia.permission_catalog_versions SET is_active = false WHERE is_active;
INSERT INTO synergia.permission_catalog_versions (version, description, is_active)
VALUES ('1.5.0', 'Triagem organizacional de feedback do produto', true);
INSERT INTO synergia.permissions
    (permission_key, resource_type, description, catalog_version, is_reserved)
VALUES ('feedback.triage', 'feedback', 'Realizar triagem de feedback', '1.5.0', true);
INSERT INTO synergia.role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM synergia.roles r
JOIN synergia.permissions p ON p.normalized_key = 'feedback.triage'
WHERE r.normalized_key = 'gestor';

CREATE TABLE synergia.feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    protocol text GENERATED ALWAYS AS ('FB-' || upper(replace(id::text, '-', ''))) STORED UNIQUE,
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    author_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    author_session_id uuid NOT NULL REFERENCES synergia.identity_sessions(id),
    kind text NOT NULL CHECK (kind IN ('bug', 'suggestion')),
    title text NOT NULL CHECK (length(btrim(title)) BETWEEN 5 AND 160),
    description text NOT NULL CHECK (length(btrim(description)) BETWEEN 10 AND 4000),
    expected_result text CHECK (length(btrim(expected_result)) BETWEEN 1 AND 2000),
    observed_result text CHECK (length(btrim(observed_result)) BETWEEN 1 AND 2000),
    source_id text NOT NULL CHECK (length(source_id) BETWEEN 1 AND 100),
    source_route text NOT NULL CHECK (
        source_route ~ '^/[A-Za-z0-9_:/-]*$' AND length(source_route) <= 160
    ),
    state text NOT NULL DEFAULT 'received' CHECK (
        state IN ('received', 'under_review', 'planned', 'resolved', 'discarded')
    ),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    last_actor_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    last_actor_session_id uuid NOT NULL REFERENCES synergia.identity_sessions(id),
    correlation_id uuid NOT NULL,
    change_reason text CHECK (length(btrim(change_reason)) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (kind = 'bug' OR (expected_result IS NULL AND observed_result IS NULL)),
    CHECK (state NOT IN ('resolved', 'discarded')
        OR (change_reason IS NOT NULL AND length(btrim(change_reason)) >= 5)),
    CHECK ((version = 1 AND state = 'received') OR version > 1)
);
CREATE INDEX feedback_author_scope_time
    ON synergia.feedback (organization_id, author_user_id, created_at DESC, id);
CREATE INDEX feedback_triage_scope_time
    ON synergia.feedback (organization_id, state, created_at DESC, id);

CREATE TABLE synergia.feedback_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feedback_id uuid NOT NULL REFERENCES synergia.feedback(id),
    actor_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    actor_session_id uuid NOT NULL REFERENCES synergia.identity_sessions(id),
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    from_state text,
    to_state text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    reason text CHECK (length(btrim(reason)) BETWEEN 1 AND 2000),
    correlation_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (feedback_id, version)
);
CREATE INDEX feedback_events_history
    ON synergia.feedback_events (feedback_id, occurred_at, id);
CREATE TRIGGER feedback_events_immutable
BEFORE UPDATE OR DELETE ON synergia.feedback_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_data_operation_event_mutation();

CREATE FUNCTION synergia.guard_feedback_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'feedback_history_is_immutable' USING ERRCODE = '23514';
    END IF;
    IF ROW(NEW.id, NEW.organization_id, NEW.author_user_id, NEW.author_session_id,
           NEW.kind, NEW.title, NEW.description, NEW.expected_result,
           NEW.observed_result, NEW.source_id, NEW.source_route, NEW.created_at)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.organization_id, OLD.author_user_id, OLD.author_session_id,
           OLD.kind, OLD.title, OLD.description, OLD.expected_result,
           OLD.observed_result, OLD.source_id, OLD.source_route, OLD.created_at)
       OR NEW.version <> OLD.version + 1 THEN
        RAISE EXCEPTION 'feedback_identity_is_immutable' USING ERRCODE = '23514';
    END IF;
    IF NOT (
        (OLD.state = 'received' AND NEW.state IN ('under_review', 'discarded'))
        OR (OLD.state = 'under_review' AND NEW.state IN ('planned', 'resolved', 'discarded'))
        OR (OLD.state = 'planned' AND NEW.state IN ('under_review', 'resolved', 'discarded'))
    ) THEN
        RAISE EXCEPTION 'feedback_transition_invalid' USING ERRCODE = '23514';
    END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
CREATE TRIGGER feedback_mutation_guard
BEFORE UPDATE OR DELETE ON synergia.feedback
FOR EACH ROW EXECUTE FUNCTION synergia.guard_feedback_mutation();

CREATE FUNCTION synergia.audit_feedback_change()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    previous_state text;
BEGIN
    previous_state := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.state END;
    INSERT INTO synergia.feedback_events (
        feedback_id, actor_user_id, actor_session_id, organization_id,
        from_state, to_state, version, reason, correlation_id
    ) VALUES (
        NEW.id, NEW.last_actor_user_id, NEW.last_actor_session_id,
        NEW.organization_id, previous_state, NEW.state, NEW.version,
        NEW.change_reason, NEW.correlation_id
    );
    -- Consolidated export (#169) uses this existing, sanitized identity source.
    -- User text and justification remain exclusively in the scoped product data.
    INSERT INTO synergia.identity_access_events (
        event_key, actor_user_id, session_id, organization_id,
        entity_type, entity_id, correlation_id, payload
    ) VALUES (
        CASE WHEN TG_OP = 'INSERT' THEN 'feedback.created'
             ELSE 'feedback.state_changed' END,
        NEW.last_actor_user_id, NEW.last_actor_session_id,
        NEW.organization_id, 'feedback', NEW.id::text, NEW.correlation_id,
        jsonb_build_object('version', NEW.version,
            'from_state', previous_state, 'to_state', NEW.state)
    );
    RETURN NEW;
END;
$$;
CREATE TRIGGER feedback_audit_created
AFTER INSERT OR UPDATE ON synergia.feedback
FOR EACH ROW EXECUTE FUNCTION synergia.audit_feedback_change();
