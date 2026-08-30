CREATE TABLE synergia.file_inspections (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source text NOT NULL CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS')),
    original_file_name text NOT NULL,
    internal_name text NOT NULL UNIQUE
        CHECK (internal_name ~ '^[0-9a-f]{48}(\.(csv|json|xlsx))?$'),
    extension text,
    declared_media_type text,
    detected_media_type text,
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    decision text NOT NULL CHECK (decision IN ('accepted', 'rejected')),
    reason_code text NOT NULL,
    analyzed_at timestamptz NOT NULL,
    retained_until timestamptz,
    discarded_at timestamptz,
    CHECK (
        (decision = 'accepted' AND reason_code = 'accepted'
            AND retained_until IS NULL AND discarded_at IS NULL)
        OR
        (decision = 'rejected' AND reason_code <> 'accepted'
            AND retained_until IS NOT NULL)
    ),
    CHECK (discarded_at IS NULL OR decision = 'rejected')
);

ALTER TABLE synergia.source_files
    ADD COLUMN inspection_id bigint UNIQUE
        REFERENCES synergia.file_inspections(id),
    ADD COLUMN detected_media_type text;

CREATE INDEX idx_file_inspections_execution
    ON synergia.file_inspections (execution_id, analyzed_at);

CREATE INDEX idx_file_inspections_retention
    ON synergia.file_inspections (retained_until)
    WHERE decision = 'rejected' AND discarded_at IS NULL;

COMMENT ON TABLE synergia.file_inspections IS
    'Decisoes auditaveis da inspecao segura; nao armazena caminhos internos';

COMMENT ON COLUMN synergia.file_inspections.original_file_name IS
    'Metadado nao confiavel informado pelo cliente; nunca usado como caminho';

CREATE OR REPLACE FUNCTION synergia.audit_file_inspection()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO synergia.audit_events (
        execution_id, entity_type, entity_id, event_type, payload
    ) VALUES (
        NEW.execution_id,
        'file_inspection',
        NEW.id::text,
        CASE WHEN NEW.decision = 'accepted'
            THEN 'file_accepted' ELSE 'file_rejected' END,
        jsonb_build_object(
            'sha256', NEW.content_hash,
            'size_bytes', NEW.size_bytes,
            'extension', NEW.extension,
            'declared_media_type', NEW.declared_media_type,
            'detected_media_type', NEW.detected_media_type,
            'decision', NEW.decision,
            'reason_code', NEW.reason_code,
            'analyzed_at', NEW.analyzed_at,
            'retained_until', NEW.retained_until
        )
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_audit_file_inspection
AFTER INSERT ON synergia.file_inspections
FOR EACH ROW EXECUTE FUNCTION synergia.audit_file_inspection();
