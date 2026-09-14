CREATE TABLE synergia.data_operation_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation text NOT NULL CHECK (
        operation IN ('backup', 'restore', 'verification', 'retention')
    ),
    outcome text NOT NULL CHECK (
        outcome IN ('started', 'succeeded', 'failed', 'refused')
    ),
    dataset text NOT NULL CHECK (
        dataset IN (
            'combined', 'database', 'accepted_uploads', 'avatars',
            'quarantine', 'security_transient'
        )
    ),
    actor_identifier text NOT NULL CHECK (
        actor_identifier ~ '^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$'
    ),
    correlation_id uuid NOT NULL,
    reason_code text CHECK (
        reason_code IS NULL OR reason_code ~ '^[a-z][a-z0-9_]{0,63}$'
    ),
    record_count bigint CHECK (record_count IS NULL OR record_count >= 0),
    artifact_count bigint CHECK (artifact_count IS NULL OR artifact_count >= 0),
    duration_ms bigint CHECK (duration_ms IS NULL OR duration_ms >= 0),
    occurred_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (outcome IN ('started', 'succeeded') AND reason_code IS NULL)
        OR (outcome IN ('failed', 'refused') AND reason_code IS NOT NULL)
    )
);

CREATE INDEX idx_data_operation_events_operation_time
    ON synergia.data_operation_events (operation, occurred_at DESC, id DESC);

CREATE FUNCTION synergia.prevent_data_operation_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'data operation events are append-only'
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER data_operation_events_immutable
BEFORE UPDATE OR DELETE ON synergia.data_operation_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_data_operation_event_mutation();

COMMENT ON TABLE synergia.data_operation_events IS
    'Historico append-only de backup, restauracao, verificacao e retencao';
COMMENT ON COLUMN synergia.data_operation_events.actor_identifier IS
    'Identidade tecnica segura; nao armazena credencial, DSN ou caminho';
COMMENT ON COLUMN synergia.data_operation_events.correlation_id IS
    'Correlacao tecnica da execucao operacional';
