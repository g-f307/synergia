DROP TRIGGER IF EXISTS data_operation_events_immutable
    ON synergia.data_operation_events;
DROP FUNCTION IF EXISTS synergia.prevent_data_operation_event_mutation();
DROP TABLE IF EXISTS synergia.data_operation_events;
