ALTER TABLE synergia.executions
    DROP CONSTRAINT executions_status_check;

ALTER TABLE synergia.executions
    ADD CONSTRAINT executions_status_check
        CHECK (status IN (
            'pending', 'running', 'completed', 'validation_failed',
            'failed', 'cancelled', 'duplicate'
        ));

COMMENT ON COLUMN synergia.executions.status IS
    'validation_failed indica que a importação foi preservada, mas está impedida de consolidar';
