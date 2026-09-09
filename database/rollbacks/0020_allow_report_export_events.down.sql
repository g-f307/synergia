DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM synergia.report_events WHERE event_type = 'report.exported'
    ) THEN
        RAISE EXCEPTION
            'cannot_rollback_report_export_events_after_export_audit_exists';
    END IF;
END;
$$;

ALTER TABLE synergia.report_events
    DROP CONSTRAINT report_events_event_type_check;

ALTER TABLE synergia.report_events
    DROP COLUMN actor_session_id;

ALTER TABLE synergia.report_events
    ADD CONSTRAINT report_events_event_type_check CHECK (event_type IN (
        'report.generation_started', 'report.generation_succeeded',
        'report.generation_failed', 'report.generation_cancelled',
        'report.consulted'
    ));

COMMENT ON TABLE synergia.report_events IS NULL;
