ALTER TABLE synergia.executions
    DROP CONSTRAINT executions_status_check;

UPDATE synergia.executions
SET status = 'validating'
WHERE status = 'running';

ALTER TABLE synergia.executions
    ADD CONSTRAINT executions_status_check
        CHECK (status IN (
            'pending', 'validating', 'validation_failed', 'normalizing',
            'consolidating', 'applying_rules', 'completed',
            'completed_with_errors', 'failed', 'reprocessing', 'duplicate',
            'cancelled'
        )),
    ADD COLUMN pipeline_version text NOT NULL DEFAULT '1.0.0',
    ADD COLUMN rule_catalog_version text NOT NULL DEFAULT '1.0.0',
    ADD COLUMN state_version bigint NOT NULL DEFAULT 0 CHECK (state_version >= 0),
    ADD COLUMN state_changed_by_type text NOT NULL DEFAULT 'system'
        CHECK (state_changed_by_type IN ('user', 'technical', 'system')),
    ADD COLUMN state_changed_by text NOT NULL DEFAULT 'migration-0009',
    ADD COLUMN state_change_reason text NOT NULL DEFAULT 'legacy_state_imported';

ALTER TABLE synergia.source_files
    DROP CONSTRAINT source_files_content_hash_key,
    ADD CONSTRAINT source_files_execution_hash_key
        UNIQUE (execution_id, content_hash);

CREATE TABLE synergia.execution_state_transitions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    from_state text,
    to_state text NOT NULL,
    actor_type text NOT NULL CHECK (actor_type IN ('user', 'technical', 'system')),
    actor_identifier text NOT NULL,
    reason text NOT NULL,
    state_version bigint NOT NULL CHECK (state_version >= 0),
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE synergia.execution_idempotency (
    request_fingerprint text PRIMARY KEY
        CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
    request_type text NOT NULL CHECK (request_type IN ('import', 'reprocess')),
    execution_id text NOT NULL UNIQUE REFERENCES synergia.executions(id),
    source_execution_id text REFERENCES synergia.executions(id),
    pipeline_version text NOT NULL,
    rule_catalog_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (request_type = 'import' AND source_execution_id IS NULL)
        OR (request_type = 'reprocess' AND source_execution_id IS NOT NULL)
    )
);

CREATE INDEX idx_execution_transitions_execution_time
    ON synergia.execution_state_transitions (execution_id, occurred_at, id);
CREATE INDEX idx_execution_idempotency_source_versions
    ON synergia.execution_idempotency (
        source_execution_id, pipeline_version, rule_catalog_version
    );
CREATE INDEX idx_executions_status_updated
    ON synergia.executions (status, updated_at);

INSERT INTO synergia.execution_state_transitions (
    execution_id, from_state, to_state, actor_type, actor_identifier,
    reason, state_version, occurred_at
)
SELECT id, NULL, status, 'system', 'migration-0009',
       'legacy_state_imported', state_version, updated_at
FROM synergia.executions;

CREATE FUNCTION synergia.validate_execution_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IS NOT DISTINCT FROM NEW.status THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.status = 'pending' AND NEW.status IN (
            'validating', 'reprocessing', 'duplicate', 'failed', 'cancelled'
        ))
        OR (OLD.status = 'reprocessing' AND NEW.status IN ('validating', 'failed'))
        OR (OLD.status = 'validating' AND NEW.status IN (
            'normalizing', 'validation_failed', 'failed'
        ))
        OR (OLD.status = 'normalizing' AND NEW.status IN (
            'consolidating', 'validation_failed', 'failed'
        ))
        OR (OLD.status = 'consolidating' AND NEW.status IN (
            'applying_rules', 'completed_with_errors', 'failed'
        ))
        OR (OLD.status = 'applying_rules' AND NEW.status IN (
            'completed', 'completed_with_errors', 'failed'
        ))
    ) THEN
        RAISE EXCEPTION 'invalid_execution_transition:%->%', OLD.status, NEW.status
            USING ERRCODE = '23514';
    END IF;

    IF NEW.state_changed_by_type IS NULL
       OR NEW.state_changed_by IS NULL OR btrim(NEW.state_changed_by) = ''
       OR NEW.state_change_reason IS NULL OR btrim(NEW.state_change_reason) = '' THEN
        RAISE EXCEPTION 'execution_transition_metadata_required'
            USING ERRCODE = '23514';
    END IF;

    NEW.state_version = OLD.state_version + 1;
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE FUNCTION synergia.audit_execution_state()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    previous_state text;
    event_name text;
BEGIN
    previous_state := CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.status END;
    IF TG_OP = 'UPDATE' AND OLD.status IS NOT DISTINCT FROM NEW.status THEN
        RETURN NEW;
    END IF;

    INSERT INTO synergia.execution_state_transitions (
        execution_id, from_state, to_state, actor_type, actor_identifier,
        reason, state_version
    ) VALUES (
        NEW.id, previous_state, NEW.status, NEW.state_changed_by_type,
        NEW.state_changed_by, NEW.state_change_reason, NEW.state_version
    );

    event_name := CASE
        WHEN NEW.status = 'validating' THEN 'execution_started'
        WHEN NEW.status IN ('completed', 'completed_with_errors')
            THEN 'execution_completed'
        WHEN NEW.status IN ('failed', 'validation_failed') THEN 'execution_failed'
        ELSE 'execution_transitioned'
    END;

    INSERT INTO synergia.audit_events (
        execution_id, entity_type, entity_id, event_type, payload
    ) VALUES (
        NEW.id, 'execution', NEW.id, event_name,
        jsonb_build_object(
            'from_state', previous_state,
            'to_state', NEW.status,
            'actor_type', NEW.state_changed_by_type,
            'actor_identifier', NEW.state_changed_by,
            'reason', NEW.state_change_reason,
            'state_version', NEW.state_version,
            'pipeline_version', NEW.pipeline_version,
            'rule_catalog_version', NEW.rule_catalog_version
        )
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER executions_validate_transition
BEFORE UPDATE OF status ON synergia.executions
FOR EACH ROW EXECUTE FUNCTION synergia.validate_execution_transition();

CREATE TRIGGER executions_audit_initial_state
AFTER INSERT ON synergia.executions
FOR EACH ROW EXECUTE FUNCTION synergia.audit_execution_state();

CREATE TRIGGER executions_audit_transition
AFTER UPDATE OF status ON synergia.executions
FOR EACH ROW EXECUTE FUNCTION synergia.audit_execution_state();

COMMENT ON TABLE synergia.execution_state_transitions IS
    'Trilha imutável de estados, responsável, motivo e versão otimista';
COMMENT ON TABLE synergia.execution_idempotency IS
    'Reserva transacional de requisições por arquivos e versões de processamento';
