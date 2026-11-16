DROP INDEX synergia.ai_maintenance_time;
DROP INDEX synergia.ai_maintenance_terminal_once;
DROP INDEX synergia.ai_maintenance_event_once;
ALTER TABLE synergia.data_operation_events DROP CONSTRAINT ai_maintenance_event_shape;
-- Keep the two admitted dataset values: immutable historical events must survive
-- rollback. Legacy code ignores these datasets; never rewrite or delete audit.
