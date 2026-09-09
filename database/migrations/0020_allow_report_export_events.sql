ALTER TABLE synergia.report_events
    DROP CONSTRAINT report_events_event_type_check;

ALTER TABLE synergia.report_events
    ADD COLUMN actor_session_id uuid REFERENCES synergia.identity_sessions(id);

ALTER TABLE synergia.report_events
    ADD CONSTRAINT report_events_event_type_check CHECK (event_type IN (
        'report.generation_started', 'report.generation_succeeded',
        'report.generation_failed', 'report.generation_cancelled',
        'report.consulted', 'report.exported'
    ));

COMMENT ON TABLE synergia.report_events IS
    'Trilha imutável da geração, consulta, cancelamento e exportação de relatórios';

COMMENT ON COLUMN synergia.report_events.actor_session_id IS
    'Sessão autenticada responsável pelo evento, quando disponível';
