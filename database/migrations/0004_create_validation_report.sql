ALTER TABLE synergia.executions
    DROP CONSTRAINT executions_status_check;

ALTER TABLE synergia.executions
    ADD CONSTRAINT executions_status_check
        CHECK (status IN (
            'pending', 'running', 'completed', 'failed', 'cancelled', 'duplicate',
            'blocked'
        ));

CREATE TABLE synergia.validation_issues (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id) ON DELETE CASCADE,
    code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('error', 'warning')),
    message text NOT NULL,
    file_name text NOT NULL,
    sheet_name text,
    row_number integer CHECK (row_number IS NULL OR row_number > 0),
    column_name text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_validation_issues_execution
    ON synergia.validation_issues (execution_id, severity);
