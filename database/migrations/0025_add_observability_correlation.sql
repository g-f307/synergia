ALTER TABLE synergia.executions
    ADD COLUMN correlation_id uuid;

ALTER TABLE synergia.audit_events
    ADD COLUMN correlation_id uuid;

UPDATE synergia.audit_events event
SET correlation_id = execution.correlation_id
FROM synergia.executions execution
WHERE execution.id = event.execution_id
  AND event.correlation_id IS NULL;

CREATE FUNCTION synergia.populate_audit_event_correlation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.correlation_id IS NULL THEN
        SELECT correlation_id INTO NEW.correlation_id
        FROM synergia.executions
        WHERE id = NEW.execution_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER audit_events_populate_correlation
BEFORE INSERT ON synergia.audit_events
FOR EACH ROW EXECUTE FUNCTION synergia.populate_audit_event_correlation();

CREATE INDEX idx_executions_correlation
    ON synergia.executions (correlation_id)
    WHERE correlation_id IS NOT NULL;
CREATE INDEX idx_audit_events_correlation
    ON synergia.audit_events (correlation_id, occurred_at DESC, id)
    WHERE correlation_id IS NOT NULL;
CREATE INDEX idx_execution_transitions_time
    ON synergia.execution_state_transitions (occurred_at DESC, id);
CREATE INDEX idx_report_events_time
    ON synergia.report_events (occurred_at DESC, id);
CREATE INDEX idx_notification_events_time
    ON synergia.notification_events (occurred_at DESC, id);
CREATE INDEX idx_email_delivery_attempts_time
    ON synergia.email_delivery_attempts (occurred_at DESC, id);
CREATE INDEX idx_approval_events_time
    ON synergia.approval_events (occurred_at DESC, id);

COMMENT ON COLUMN synergia.executions.correlation_id IS
    'Identificador tecnico da requisicao que iniciou a execucao; nao identifica usuario';
COMMENT ON COLUMN synergia.audit_events.correlation_id IS
    'Correlacao tecnica com a requisicao e logs; auditoria permanece trilha de negocio';
