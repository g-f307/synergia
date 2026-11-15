-- Internal results only: no prompt, context or raw model output.
CREATE FUNCTION synergia.ai_assistance_result_shape_valid(document jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE item jsonb; ref jsonb;
BEGIN
    IF document IS NULL THEN RETURN true; END IF;
    IF jsonb_typeof(document) IS DISTINCT FROM 'object'
       OR NOT (document ?& ARRAY['assistance_id','execution_id','state','summary',
           'findings','human_checks','limitations','provenance','created_at'])
       OR document - ARRAY['assistance_id','execution_id','state','summary',
           'findings','human_checks','limitations','provenance','created_at'] <> '{}'::jsonb
       OR jsonb_typeof(document->'findings') IS DISTINCT FROM 'array'
       OR jsonb_typeof(document->'human_checks') IS DISTINCT FROM 'array'
       OR jsonb_typeof(document->'limitations') IS DISTINCT FROM 'array'
       OR jsonb_typeof(document->'provenance') IS DISTINCT FROM 'object'
       OR jsonb_typeof(document->'summary') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'assistance_id') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'execution_id') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'created_at') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'state') IS DISTINCT FROM 'string'
       OR document->>'assistance_id' !~ '^[0-9a-f-]{36}$'
       OR document->>'execution_id' !~ '^[0-9a-f-]{36}$'
       OR document->>'created_at' !~ '^[0-9T:.+Z-]{20,40}$'
       OR document->>'state' NOT IN ('ready', 'insufficient_evidence', 'rejected')
       OR document::text ~* '(password|secret|bearer|token|eyJ[A-Za-z0-9_-]{10})'
    THEN RETURN false; END IF;
    IF document->>'summary' NOT IN (
        'Os fatos autorizados estão disponíveis para conferência humana.',
        'As evidências disponíveis são insuficientes.',
        'A resposta gerada foi recusada pela validação.'
    ) AND document->>'summary' !~
       '^(A execução registra|Foram registrados) [0-9]{1,19} (erro|erros), [0-9]{1,19} (aviso|avisos) e [0-9]{1,19} (pendência|pendências)\.( Referências disponíveis: (DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}(, (DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}){0,2}\.)?$'
    THEN RETURN false; END IF;
    IF NOT (document->'provenance' ?& ARRAY['contract_version','model','digest',
            'context_hash','prompt_hash','origin','timings'])
       OR (document->'provenance') - ARRAY['contract_version','model','digest',
            'context_hash','prompt_hash','origin','timings'] <> '{}'::jsonb
       OR jsonb_typeof(document->'provenance'->'timings') IS DISTINCT FROM 'object'
       OR NOT (document->'provenance'->'timings' ?& ARRAY['context_ms','generation_ms','total_ms'])
       OR (document->'provenance'->'timings') - ARRAY['context_ms','generation_ms','total_ms'] <> '{}'::jsonb
       OR jsonb_typeof(document->'provenance'->'model') NOT IN ('string', 'null')
       OR jsonb_typeof(document->'provenance'->'digest') NOT IN ('string', 'null')
       OR jsonb_typeof(document->'provenance'->'context_hash') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'prompt_hash') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'origin') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'contract_version') IS DISTINCT FROM 'string'
       OR jsonb_typeof(document->'provenance'->'timings'->'context_ms') IS DISTINCT FROM 'number'
       OR jsonb_typeof(document->'provenance'->'timings'->'generation_ms') IS DISTINCT FROM 'number'
       OR jsonb_typeof(document->'provenance'->'timings'->'total_ms') IS DISTINCT FROM 'number'
       OR (document->'provenance'->>'model' IS NOT NULL AND
           document->'provenance'->>'model' !~ '^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$')
       OR (document->'provenance'->>'digest' IS NOT NULL AND
           document->'provenance'->>'digest' !~ '^sha256:[a-f0-9]{64}$')
       OR document->'provenance'->>'context_hash' !~ '^[a-f0-9]{64}$'
       OR document->'provenance'->>'prompt_hash' !~ '^[a-f0-9]{64}$'
       OR document->'provenance'->>'contract_version' <> '1.0.0'
       OR document->'provenance'->>'origin' NOT IN ('model', 'deterministic')
    THEN RETURN false; END IF;
    FOR item IN SELECT * FROM jsonb_array_elements(document->'findings') LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'object'
           OR NOT (item ?& ARRAY['title','explanation','evidence_refs'])
           OR item - ARRAY['title','explanation','evidence_refs'] <> '{}'::jsonb
           OR jsonb_typeof(item->'evidence_refs') IS DISTINCT FROM 'array'
           OR jsonb_typeof(item->'title') IS DISTINCT FROM 'string'
           OR jsonb_typeof(item->'explanation') IS DISTINCT FROM 'string'
           OR item->>'title' NOT IN ('Registros disponíveis', 'Registros para conferência',
               'Divergência registrada', 'Pendência registrada', 'Classificação registrada',
               'Evidência registrada', 'Transição registrada')
           OR item->>'explanation' NOT IN ('Há um registro disponível para conferência.',
               'Há registros disponíveis para conferência.',
               'Os registros estão disponíveis para conferência.')
        THEN RETURN false; END IF;
        IF jsonb_array_length(item->'evidence_refs') NOT BETWEEN 1 AND 3
        THEN RETURN false; END IF;
        FOR ref IN SELECT * FROM jsonb_array_elements(item->'evidence_refs') LOOP
            IF jsonb_typeof(ref) IS DISTINCT FROM 'string'
               OR (ref #>> '{}') !~ '^(DIV|PEN|CLA|EVI|HIS)-[a-f0-9]{32}$'
            THEN RETURN false; END IF;
        END LOOP;
    END LOOP;
    FOR item IN SELECT * FROM jsonb_array_elements(document->'human_checks')
                UNION ALL SELECT * FROM jsonb_array_elements(document->'limitations') LOOP
        IF jsonb_typeof(item) IS DISTINCT FROM 'string' OR (item #>> '{}') NOT IN (
            'A conferência humana das evidências é necessária.',
            'Conferência humana das referências disponíveis.',
            'Conferência humana das evidências disponíveis.',
            'O contexto possui seções truncadas.', 'A execução terminou com falha.',
            'Há dados ausentes ou indisponíveis no contexto.',
            'As evidências disponíveis são insuficientes.',
            'Assistência gerada por IA: pode conter erros. A conferência humana das evidências é necessária.'
        ) THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END $$;

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
    result jsonb CHECK (synergia.ai_assistance_result_shape_valid(result)),
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
