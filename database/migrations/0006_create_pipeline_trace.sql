CREATE TABLE synergia.imported_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    sheet_name text NOT NULL,
    row_number integer NOT NULL CHECK (row_number > 1),
    original_values jsonb NOT NULL,
    processing_status text NOT NULL
        CHECK (processing_status IN ('valid', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_file_id, sheet_name, row_number),
    UNIQUE (id, execution_id, source_file_id),
    CHECK (jsonb_typeof(original_values) = 'object')
);

CREATE TABLE synergia.pipeline_issues (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    imported_record_id bigint,
    scope text NOT NULL CHECK (scope IN ('file', 'structure', 'record')),
    severity text NOT NULL CHECK (severity IN ('error', 'warning')),
    code text NOT NULL,
    sheet_name text,
    row_number integer,
    column_name text,
    reason text NOT NULL,
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (imported_record_id, execution_id, source_file_id)
        REFERENCES synergia.imported_records(id, execution_id, source_file_id)
);

CREATE TABLE synergia.pipeline_summaries (
    execution_id text PRIMARY KEY REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL UNIQUE REFERENCES synergia.source_files(id),
    rows_read integer NOT NULL CHECK (rows_read >= 0),
    valid_records integer NOT NULL CHECK (valid_records >= 0),
    rejected_records integer NOT NULL CHECK (rejected_records >= 0),
    normalized_records integer NOT NULL CHECK (normalized_records >= 0),
    error_count integer NOT NULL CHECK (error_count >= 0),
    warning_count integer NOT NULL CHECK (warning_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (valid_records + rejected_records = rows_read),
    CHECK (normalized_records = valid_records)
);

ALTER TABLE synergia.normalized_records
    ADD COLUMN imported_record_id bigint,
    ADD CONSTRAINT normalized_records_imported_record_fk
        FOREIGN KEY (imported_record_id, execution_id, source_file_id)
        REFERENCES synergia.imported_records(id, execution_id, source_file_id);

CREATE UNIQUE INDEX idx_normalized_records_imported
    ON synergia.normalized_records (imported_record_id);
CREATE INDEX idx_imported_records_execution
    ON synergia.imported_records (execution_id);
CREATE INDEX idx_pipeline_issues_execution
    ON synergia.pipeline_issues (execution_id);

COMMENT ON TABLE synergia.pipeline_issues IS
    'Erros e avisos persistentes classificados por arquivo, estrutura ou registro';
