CREATE TABLE synergia.normalized_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    sheet_name text NOT NULL,
    row_number integer NOT NULL CHECK (row_number > 0),
    normalized_values jsonb NOT NULL,
    original_values jsonb NOT NULL,
    transformations jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_file_id, sheet_name, row_number),
    CHECK (jsonb_typeof(normalized_values) = 'object'),
    CHECK (jsonb_typeof(original_values) = 'object'),
    CHECK (jsonb_typeof(transformations) = 'array')
);

CREATE INDEX idx_normalized_records_execution
    ON synergia.normalized_records (execution_id);

COMMENT ON TABLE synergia.normalized_records IS
    'Representação interna normalizada, com originais e transformações auditáveis';
