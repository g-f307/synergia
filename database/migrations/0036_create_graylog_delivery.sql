-- The network is never consulted by these triggers. Only source keys are queued.
CREATE TABLE synergia.observability_events (
    id uuid PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    action text NOT NULL CHECK (action IN ('llm.requested', 'llm.completed', 'llm.failed')),
    actor_user_id uuid REFERENCES synergia.identity_users(id),
    correlation_id uuid NOT NULL,
    operation_id uuid NOT NULL,
    model_name text NOT NULL CHECK (model_name = 'qwen3:4b-instruct'),
    model_digest text NOT NULL CHECK (model_digest ~ '^[0-9a-f]{64}$'),
    duration_ms bigint CHECK (duration_ms >= 0),
    fallback boolean NOT NULL DEFAULT false,
    UNIQUE (operation_id, action)
);
CREATE TRIGGER observability_events_immutable
BEFORE UPDATE OR DELETE ON synergia.observability_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_data_operation_event_mutation();

ALTER VIEW synergia.audit_event_catalog RENAME TO audit_event_catalog_v1;
CREATE VIEW synergia.audit_event_catalog AS
SELECT * FROM synergia.audit_event_catalog_v1
UNION ALL
SELECT 'llm:' || id, occurred_at, NULL::uuid, actor_user_id, 'user',
       action, 'llm_operation', operation_id::text,
       CASE WHEN action = 'llm.failed' THEN 'failure'
            WHEN action = 'llm.requested' THEN 'started' ELSE 'success' END,
       correlation_id,
       jsonb_build_object('model', model_name, 'model_digest', model_digest,
           'duration_ms', duration_ms, 'fallback', fallback,
           'executor', 'synergia-api', 'operation', 'quality_explanation',
           'tool', 'none'),
       'observability_events'
FROM synergia.observability_events
UNION ALL
SELECT 'security_rate:' || id, occurred_at, NULL::uuid, NULL::uuid, 'unknown',
       'security.rate_limit_denied', 'security_control', 'rate_limit',
       'failure', correlation_id, '{}'::jsonb, 'rate_limit_events'
FROM synergia.rate_limit_events;

CREATE TABLE synergia.graylog_control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    destination_hash text NOT NULL CHECK (destination_hash ~ '^[0-9a-f]{64}$'),
    last_run_at timestamptz
);
CREATE TABLE synergia.graylog_deliveries (
    event_key text PRIMARY KEY,
    origin text NOT NULL,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    event_id text UNIQUE,
    source_snapshot jsonb,
    payload jsonb CHECK (payload IS NULL OR jsonb_typeof(payload) = 'object'),
    state text NOT NULL DEFAULT 'pending' CHECK (state IN
        ('pending', 'inflight', 'accepted', 'uncertain', 'blocked', 'exhausted')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_code text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    accepted_at timestamptz,
    confirmed_at timestamptz
);
CREATE INDEX graylog_deliveries_pending ON synergia.graylog_deliveries
    (next_attempt_at, created_at, event_key) WHERE state = 'pending';
CREATE TABLE synergia.graylog_delivery_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key text NOT NULL REFERENCES synergia.graylog_deliveries(event_key),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    action text NOT NULL CHECK (action IN
        ('intent', 'accepted', 'pending', 'uncertain', 'blocked', 'exhausted',
         'confirm_received', 'confirm_absent', 'requeue')),
    code text NOT NULL,
    operator_id uuid,
    evidence_id uuid
);
CREATE TRIGGER graylog_history_immutable
BEFORE UPDATE OR DELETE ON synergia.graylog_delivery_history
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_data_operation_event_mutation();
CREATE TABLE synergia.graylog_scan_windows (
    origin text NOT NULL,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL CHECK (window_end > window_start),
    cursor_time timestamptz,
    cursor_key text,
    completed boolean NOT NULL DEFAULT false,
    operator_id uuid NOT NULL,
    evidence_id uuid NOT NULL,
    PRIMARY KEY (origin, window_start, window_end)
);

CREATE FUNCTION synergia.enqueue_graylog_source() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, synergia AS $$
DECLARE
    raw jsonb := to_jsonb(NEW);
    projection jsonb;
    org uuid;
    actor uuid;
    actor_type text := 'system';
    action text;
    resource_type text;
    resource_id text;
    outcome text := 'success';
    metadata jsonb := '{}'::jsonb;
BEGIN
    -- Direct primary-key joins: never scan the concatenated IDs of the UNION
    -- view for each inserted row. Only the existing canonical fields are copied.
    actor := (raw->>'actor_user_id')::uuid;
    IF actor IS NOT NULL THEN actor_type := 'user'; END IF;
    CASE TG_TABLE_NAME
    WHEN 'audit_events' THEN
        SELECT organization_id INTO org FROM synergia.executions
        WHERE id = raw->>'execution_id';
        IF COALESCE(raw->'payload'->>'actor_identifier', '') ~
            '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        THEN actor := (raw->'payload'->>'actor_identifier')::uuid; END IF;
        actor_type := CASE WHEN raw->'payload'->>'actor_type' = 'user' THEN 'user'
            WHEN raw->'payload'->>'actor_type' IN ('technical', 'system')
            THEN 'system' ELSE 'unknown' END;
        action := raw->>'event_type'; resource_type := raw->>'entity_type';
        resource_id := raw->>'entity_id';
        outcome := CASE WHEN action ~ '(failed|rejected)$' THEN 'failure'
            WHEN action IN ('execution_started', 'execution_transitioned')
            THEN 'started' ELSE 'success' END;
        metadata := jsonb_build_object('from_state', raw->'payload'->'from_state',
            'to_state', raw->'payload'->'to_state',
            'state_version', raw->'payload'->'state_version',
            'version', raw->'payload'->'version');
    WHEN 'identity_access_events' THEN
        org := (raw->>'organization_id')::uuid;
        IF actor IS NULL THEN actor_type := 'unknown'; END IF;
        action := raw->>'event_key'; resource_type := raw->>'entity_type';
        resource_id := raw->>'entity_id';
        IF action ~ '(failed|denied|blocked|replay_detected|reused|rate_limited)$'
        THEN outcome := 'failure'; END IF;
    WHEN 'report_events' THEN
        SELECT organization_id, jsonb_build_object('format', raw->'payload'->'format',
            'version', version) INTO org, metadata FROM synergia.report_versions
        WHERE id = (raw->>'report_version_id')::uuid;
        action := raw->>'event_type'; resource_type := 'report_version';
        resource_id := raw->>'report_version_id';
        outcome := CASE WHEN action = 'report.generation_failed' THEN 'failure'
            WHEN action = 'report.generation_started' THEN 'started' ELSE 'success' END;
    WHEN 'approval_events' THEN
        org := (raw->>'organization_id')::uuid; actor_type := 'user';
        action := 'approval.' || (raw->>'event_type');
        resource_type := 'approval_request'; resource_id := raw->>'request_id';
        metadata := jsonb_build_object('from_state', raw->'from_state',
            'to_state', raw->'to_state', 'version', raw->'request_version',
            'consent', raw->'consent');
    WHEN 'notification_events' THEN
        SELECT organization_id INTO org FROM synergia.notifications
        WHERE id = (raw->>'notification_id')::uuid;
        action := raw->>'event_type'; resource_type := 'notification';
        resource_id := COALESCE(raw->>'notification_id', raw->>'id');
        IF action = 'notification.delivery_failed' THEN outcome := 'failure'; END IF;
    WHEN 'notification_template_events' THEN
        action := raw->>'event_type'; resource_type := 'notification_template';
        resource_id := raw->>'revision_id';
    WHEN 'data_operation_events' THEN
        actor := NULL; actor_type := 'system'; action := 'data.' || (raw->>'operation');
        resource_type := 'dataset'; resource_id := raw->>'dataset';
        outcome := CASE WHEN raw->>'outcome' IN ('failed', 'refused') THEN 'failure'
            WHEN raw->>'outcome' = 'started' THEN 'started' ELSE 'success' END;
        metadata := jsonb_build_object('record_count', raw->'record_count',
            'artifact_count', raw->'artifact_count', 'duration_ms', raw->'duration_ms');
    WHEN 'approval_policy_activation_events' THEN
        actor := NULL; actor_type := 'system'; action := 'approval.policy_activation';
        resource_type := 'approval_policy'; resource_id := raw->>'policy_key';
        metadata := jsonb_build_object('version', raw->'policy_version',
            'is_active', raw->'is_active');
    WHEN 'email_delivery_attempts', 'email_delivery_reconciliations' THEN
        SELECT n.organization_id INTO org FROM synergia.email_deliveries d
        JOIN synergia.notifications n ON n.id = d.notification_id
        WHERE d.id = (raw->>'delivery_id')::uuid;
        actor := NULL; actor_type := 'system'; resource_type := 'email_delivery';
        resource_id := raw->>'delivery_id';
        metadata := jsonb_build_object('attempt_number', raw->'attempt_number');
        IF TG_TABLE_NAME = 'email_delivery_reconciliations' THEN
            action := 'email.reconciled';
            metadata := metadata || jsonb_build_object('to_state', raw->'resulting_state');
        ELSE
            action := 'email.' || (raw->>'outcome');
            outcome := CASE WHEN raw->>'outcome' IN ('failed', 'retry') THEN 'failure'
                WHEN raw->>'outcome' = 'started' THEN 'started' ELSE 'success' END;
        END IF;
    WHEN 'audit_export_events' THEN
        org := (raw->>'organization_id')::uuid; actor_type := 'user';
        action := 'audit.export_' || (raw->>'action'); resource_type := 'audit_export';
        resource_id := raw->>'export_id';
        outcome := CASE WHEN raw->>'action' = 'failed' THEN 'failure'
            WHEN raw->>'action' = 'requested' THEN 'started' ELSE 'success' END;
        metadata := jsonb_build_object('format', raw->'export_format',
            'event_count', raw->'event_count');
    WHEN 'observability_events' THEN
        actor_type := 'user'; action := raw->>'action'; resource_type := 'llm_operation';
        resource_id := raw->>'operation_id';
        outcome := CASE WHEN action = 'llm.failed' THEN 'failure'
            WHEN action = 'llm.requested' THEN 'started' ELSE 'success' END;
        metadata := jsonb_build_object('model', raw->'model_name',
            'model_digest', raw->'model_digest', 'duration_ms', raw->'duration_ms',
            'fallback', raw->'fallback', 'executor', 'synergia-api',
            'operation', 'quality_explanation', 'tool', 'none');
    WHEN 'rate_limit_events' THEN
        actor := NULL; actor_type := 'unknown'; action := 'security.rate_limit_denied';
        resource_type := 'security_control'; resource_id := 'rate_limit';
        outcome := 'failure';
    END CASE;
    -- A malformed value under an approved key must not copy nested payloads
    -- into the checkpoint. Python applies the authoritative policy again.
    SELECT COALESCE(jsonb_object_agg(key, value), '{}'::jsonb) INTO metadata
    FROM jsonb_each(COALESCE(metadata, '{}'::jsonb)) fields
    WHERE (key IN ('version', 'state_version', 'record_count', 'artifact_count',
            'duration_ms', 'attempt_number', 'event_count')
        AND CASE WHEN jsonb_typeof(value) = 'number'
                AND value::text ~ '^[0-9]{1,19}$'
            THEN value::text::numeric <= 9223372036854775807 ELSE false END)
       OR (key IN ('consent', 'is_active', 'fallback') AND jsonb_typeof(value) = 'boolean')
       OR (key IN ('from_state', 'to_state') AND value #>> '{}' IN
           ('pending', 'validating', 'validation_failed', 'normalizing', 'consolidating',
            'applying_rules', 'completed', 'completed_with_errors', 'failed',
            'reprocessing', 'duplicate', 'cancelled', 'draft', 'submitted',
            'in_review', 'approved', 'rejected', 'returned', 'queued', 'processing',
            'sent', 'retry'))
       OR (key = 'format' AND value #>> '{}' IN ('json', 'csv'))
       OR (TG_TABLE_NAME = 'observability_events' AND (
            (key = 'model' AND value = '"qwen3:4b-instruct"'::jsonb)
            OR (key = 'executor' AND value = '"synergia-api"'::jsonb)
            OR (key = 'operation' AND value = '"quality_explanation"'::jsonb)
            OR (key = 'tool' AND value = '"none"'::jsonb)
            OR (key = 'model_digest' AND jsonb_typeof(value) = 'string'
                AND value #>> '{}' ~ '^[0-9a-f]{64}$')));
    IF resource_id IS NULL OR NOT (
        resource_id ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$'
        OR (length(resource_id) <= 128 AND position('..' in resource_id) = 0
            AND resource_id ~ '^/[A-Za-z0-9_/{}/-]+$'))
        OR resource_id ~* '(bearer|password|passwd|secret|cookie|token|eyJ[A-Za-z0-9_-]*\.)'
        OR resource_type ~* '(bearer|password|passwd|secret|cookie|token)'
    THEN resource_id := '[redacted]'; END IF;
    projection := jsonb_build_object('id', TG_ARGV[0] || ':' || NEW.id::text,
        'occurred_at', raw->TG_ARGV[1], 'organization_id', org, 'actor_id', actor,
        'actor_type', actor_type, 'action', action, 'resource_type', resource_type,
        'resource_id', resource_id, 'outcome', outcome,
        'correlation_id', raw->'correlation_id', 'metadata', metadata,
        'origin', TG_TABLE_NAME);
    INSERT INTO synergia.graylog_deliveries (event_key, origin, occurred_at, source_snapshot)
    VALUES (TG_ARGV[0] || ':' || NEW.id::text, TG_TABLE_NAME,
        (to_jsonb(NEW)->>TG_ARGV[1])::timestamptz, projection)
    ON CONFLICT (event_key) DO NOTHING;
    RETURN NEW;
END $$;
DO $$
DECLARE source record;
BEGIN
    FOR source IN SELECT * FROM (VALUES
        ('audit_events', 'execution', 'occurred_at'),
        ('identity_access_events', 'identity', 'occurred_at'),
        ('report_events', 'report', 'occurred_at'),
        ('approval_events', 'approval', 'occurred_at'),
        ('notification_events', 'notification', 'occurred_at'),
        ('notification_template_events', 'template', 'occurred_at'),
        ('data_operation_events', 'data_operation', 'occurred_at'),
        ('approval_policy_activation_events', 'policy', 'changed_at'),
        ('email_delivery_attempts', 'email_attempt', 'occurred_at'),
        ('email_delivery_reconciliations', 'email_reconciliation', 'occurred_at'),
        ('audit_export_events', 'audit_export', 'occurred_at'),
        ('observability_events', 'llm', 'occurred_at'),
        ('rate_limit_events', 'security_rate', 'occurred_at')
    ) AS sources(table_name, prefix, time_column)
    LOOP
        EXECUTE format('CREATE TRIGGER graylog_source_insert AFTER INSERT ON synergia.%I '
            'FOR EACH ROW EXECUTE FUNCTION synergia.enqueue_graylog_source(%L, %L)',
            source.table_name, source.prefix, source.time_column);
    END LOOP;
END $$;
COMMENT ON TABLE synergia.graylog_deliveries IS
    'Durable projection checkpoint; no raw event payloads, credentials or responses';
