-- Reuse immutable data-operation audit and its existing transactional Graylog outbox.
ALTER TABLE synergia.data_operation_events
    DROP CONSTRAINT data_operation_events_dataset_check;
ALTER TABLE synergia.data_operation_events ADD CONSTRAINT data_operation_events_dataset_check
    CHECK (dataset IN ('combined', 'database', 'accepted_uploads', 'avatars',
        'quarantine', 'security_transient',
        'ai_assistance_results', 'ai_assistance_reservations'));
ALTER TABLE synergia.data_operation_events ADD CONSTRAINT ai_maintenance_event_shape
    CHECK (dataset NOT IN ('ai_assistance_results', 'ai_assistance_reservations') OR (
        operation = 'retention' AND outcome IN ('started', 'succeeded', 'failed')
        AND (record_count IS NULL OR record_count BETWEEN 0 AND 1000)
        AND (reason_code IS NULL OR reason_code IN
            ('maintenance_failed', 'configuration_invalid', 'database_unavailable', 'actor_not_found'))
        AND ((outcome = 'started' AND record_count IS NULL AND duration_ms IS NULL)
            OR (outcome = 'succeeded' AND record_count IS NOT NULL AND duration_ms IS NOT NULL)
            OR (outcome = 'failed' AND duration_ms IS NOT NULL))
    ));
CREATE UNIQUE INDEX ai_maintenance_event_once
    ON synergia.data_operation_events (correlation_id, outcome)
    WHERE dataset IN ('ai_assistance_results', 'ai_assistance_reservations');
CREATE UNIQUE INDEX ai_maintenance_terminal_once
    ON synergia.data_operation_events (correlation_id)
    WHERE dataset IN ('ai_assistance_results', 'ai_assistance_reservations')
      AND outcome IN ('succeeded', 'failed');
CREATE INDEX ai_maintenance_time
    ON synergia.data_operation_events (dataset, occurred_at DESC, id DESC)
    WHERE dataset IN ('ai_assistance_results', 'ai_assistance_reservations');
