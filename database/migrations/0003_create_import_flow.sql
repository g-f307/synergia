ALTER TABLE synergia.executions
    DROP CONSTRAINT executions_status_check;

ALTER TABLE synergia.executions
    ADD CONSTRAINT executions_status_check
        CHECK (status IN (
            'pending', 'running', 'completed', 'failed', 'cancelled', 'duplicate'
        )),
    ADD COLUMN source text
        CHECK (source IN ('N-FP', 'OWM', 'GMES/OQC', 'TMS')),
    ADD COLUMN actor_type text
        CHECK (actor_type IN ('user', 'technical')),
    ADD COLUMN actor_identifier text,
    ADD COLUMN failure_reason text,
    ADD COLUMN duplicate_of_execution_id text REFERENCES synergia.executions(id),
    ADD CONSTRAINT executions_actor_complete CHECK (
        (actor_type IS NULL AND actor_identifier IS NULL)
        OR (actor_type IS NOT NULL AND actor_identifier IS NOT NULL)
    ),
    ADD CONSTRAINT executions_duplicate_not_self CHECK (
        duplicate_of_execution_id IS NULL OR duplicate_of_execution_id <> id
    );

ALTER TABLE synergia.source_files
    ADD COLUMN extension text CHECK (extension ~ '^[a-z0-9]+$'),
    ADD COLUMN storage_key text UNIQUE;

CREATE INDEX idx_executions_source ON synergia.executions (source);
CREATE INDEX idx_executions_duplicate ON synergia.executions (duplicate_of_execution_id);

COMMENT ON COLUMN synergia.source_files.storage_key IS
    'Chave relativa no diretório controlado; o caminho absoluto não é exposto pela API';
