-- Internal results only: no prompt, context or raw model output.
CREATE TABLE synergia.ai_assistances (
    id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    requested_by uuid NOT NULL REFERENCES synergia.identity_users(id),
    state text NOT NULL CHECK (state IN ('processing', 'ready', 'insufficient_evidence', 'rejected')),
    origin text CHECK (origin IN ('model', 'deterministic')),
    contract_version text NOT NULL CHECK (contract_version = '1.0.0'),
    model_name text CHECK (model_name ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$'),
    model_digest text CHECK (model_digest ~ '^sha256:[a-f0-9]{64}$'),
    context_sha256 text NOT NULL CHECK (context_sha256 ~ '^[a-f0-9]{64}$'),
    prompt_sha256 text NOT NULL CHECK (prompt_sha256 ~ '^[a-f0-9]{64}$'),
    response_sha256 text CHECK (response_sha256 ~ '^[a-f0-9]{64}$'),
    rejection_code text CHECK (rejection_code IN (
        'runtime_busy', 'runtime_timeout', 'runtime_unavailable', 'runtime_pin_mismatch',
        'runtime_redirect', 'runtime_response_too_large', 'runtime_invalid_response',
        'response_too_large', 'invalid_json', 'invalid_schema', 'invalid_reference',
        'ungrounded_summary', 'ungrounded_finding', 'ungrounded_checks',
        'ungrounded_limitations', 'missing_limitations'
    )),
    result jsonb CHECK (jsonb_typeof(result) = 'object'),
    elapsed_ms integer CHECK (elapsed_ms BETWEEN 0 AND 30000),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    expires_at timestamptz NOT NULL,
    reservation_until timestamptz,
    CHECK ((model_name IS NULL) = (model_digest IS NULL)),
    CHECK (expires_at > created_at),
    CHECK (completed_at IS NULL OR completed_at >= created_at),
    CHECK (
      (state = 'processing' AND origin IS NULL AND result IS NULL AND completed_at IS NULL
       AND reservation_until IS NOT NULL AND elapsed_ms IS NULL AND rejection_code IS NULL
       AND response_sha256 IS NULL)
      OR
      (state = 'ready' AND origin = 'model' AND result IS NOT NULL AND completed_at IS NOT NULL
       AND reservation_until IS NULL AND elapsed_ms IS NOT NULL AND rejection_code IS NULL
       AND response_sha256 IS NOT NULL AND model_digest IS NOT NULL)
      OR
      (state = 'insufficient_evidence' AND origin = 'deterministic' AND result IS NOT NULL
       AND completed_at IS NOT NULL AND reservation_until IS NULL AND elapsed_ms IS NOT NULL
       AND rejection_code IS NULL AND response_sha256 IS NULL)
      OR
      (state = 'rejected' AND origin = 'deterministic' AND result IS NOT NULL
       AND completed_at IS NOT NULL AND reservation_until IS NULL AND elapsed_ms IS NOT NULL
       AND rejection_code IS NOT NULL)
    )
);
CREATE UNIQUE INDEX ai_assistance_idempotency ON synergia.ai_assistances
    (organization_id, execution_id, context_sha256, prompt_sha256, model_digest, contract_version)
    NULLS NOT DISTINCT;
CREATE INDEX ai_assistance_latest ON synergia.ai_assistances
    (organization_id, execution_id, created_at DESC);
CREATE INDEX ai_assistance_expiry ON synergia.ai_assistances (expires_at, id);
CREATE INDEX ai_assistance_reservations ON synergia.ai_assistances (reservation_until)
    WHERE state = 'processing';

-- Immutable metadata-only audit survives removal of the result.
CREATE TABLE synergia.ai_assistance_events (
    id uuid PRIMARY KEY,
    assistance_id uuid NOT NULL,
    execution_id text NOT NULL,
    organization_id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    correlation_id uuid NOT NULL,
    action text NOT NULL CHECK (action IN ('requested', 'reused', 'completed', 'rejected', 'read', 'expired', 'integrity_error')),
    state text NOT NULL CHECK (state IN ('processing', 'ready', 'insufficient_evidence', 'rejected')),
    origin text CHECK (origin IN ('model', 'deterministic')),
    contract_version text NOT NULL CHECK (contract_version = '1.0.0'),
    model_name text CHECK (model_name ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$'),
    model_digest text CHECK (model_digest ~ '^sha256:[a-f0-9]{64}$'),
    context_sha256 text NOT NULL CHECK (context_sha256 ~ '^[a-f0-9]{64}$'),
    prompt_sha256 text NOT NULL CHECK (prompt_sha256 ~ '^[a-f0-9]{64}$'),
    response_sha256 text CHECK (response_sha256 ~ '^[a-f0-9]{64}$'),
    rejection_code text CHECK (rejection_code IN (
        'runtime_busy', 'runtime_timeout', 'runtime_unavailable', 'runtime_pin_mismatch',
        'runtime_redirect', 'runtime_response_too_large', 'runtime_invalid_response',
        'response_too_large', 'invalid_json', 'invalid_schema', 'invalid_reference',
        'ungrounded_summary', 'ungrounded_finding', 'ungrounded_checks',
        'ungrounded_limitations', 'missing_limitations'
    )),
    elapsed_ms integer CHECK (elapsed_ms BETWEEN 0 AND 30000),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX ai_assistance_events_scope_time ON synergia.ai_assistance_events
    (organization_id, occurred_at, id);
CREATE TRIGGER ai_assistance_events_immutable BEFORE UPDATE OR DELETE
    ON synergia.ai_assistance_events FOR EACH ROW
    EXECUTE FUNCTION synergia.prevent_data_operation_event_mutation();

ALTER VIEW synergia.audit_event_catalog RENAME TO audit_event_catalog_v2;
CREATE VIEW synergia.audit_event_catalog AS
SELECT * FROM synergia.audit_event_catalog_v2
UNION ALL
SELECT 'ai_assistance:' || id, occurred_at, organization_id, actor_user_id, 'user',
    'ai.assistance.' || action, 'ai_assistance', assistance_id::text,
    CASE WHEN action = 'requested' THEN 'started' WHEN action IN ('rejected', 'integrity_error') THEN 'failure'
         ELSE 'success' END, correlation_id,
    jsonb_build_object('execution_id', execution_id, 'state', state, 'origin', origin,
        'contract_version', contract_version, 'model_name', model_name,
        'model_digest', model_digest, 'context_sha256', context_sha256,
        'prompt_sha256', prompt_sha256, 'response_sha256', response_sha256,
        'rejection_code', rejection_code, 'duration_ms', elapsed_ms),
    'ai_assistance_events' FROM synergia.ai_assistance_events;

CREATE FUNCTION synergia.enqueue_ai_assistance_audit() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, synergia AS $$
BEGIN
    INSERT INTO synergia.graylog_deliveries (event_key, origin, occurred_at, source_snapshot)
    VALUES ('ai_assistance:' || NEW.id::text, 'ai_assistance_events', NEW.occurred_at,
        jsonb_build_object('id', 'ai_assistance:' || NEW.id::text,
            'occurred_at', NEW.occurred_at, 'organization_id', NEW.organization_id,
            'actor_id', NEW.actor_user_id, 'actor_type', 'user',
            'action', 'ai.assistance.' || NEW.action, 'resource_type', 'ai_assistance',
            'resource_id', NEW.assistance_id::text,
            'outcome', CASE WHEN NEW.action = 'requested' THEN 'started'
                       WHEN NEW.action IN ('rejected', 'integrity_error') THEN 'failure'
                       ELSE 'success' END,
            'correlation_id', NEW.correlation_id, 'origin', 'ai_assistance_events',
            'metadata', jsonb_build_object('execution_id', NEW.execution_id,
                'state', NEW.state, 'origin', NEW.origin,
                'contract_version', NEW.contract_version, 'model_name', NEW.model_name,
                'model_digest', NEW.model_digest, 'context_sha256', NEW.context_sha256,
                'prompt_sha256', NEW.prompt_sha256, 'response_sha256', NEW.response_sha256,
                'rejection_code', NEW.rejection_code, 'duration_ms', NEW.elapsed_ms)))
    ON CONFLICT (event_key) DO NOTHING;
    RETURN NEW;
END $$;
CREATE TRIGGER graylog_ai_assistance_insert AFTER INSERT ON synergia.ai_assistance_events
    FOR EACH ROW EXECUTE FUNCTION synergia.enqueue_ai_assistance_audit();
