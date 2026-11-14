DROP TRIGGER graylog_ai_assistance_insert ON synergia.ai_assistance_events;
DROP FUNCTION synergia.enqueue_ai_assistance_audit();
DROP VIEW synergia.audit_event_catalog;
ALTER VIEW synergia.audit_event_catalog_v2 RENAME TO audit_event_catalog;
DROP TABLE synergia.ai_assistance_events;
DROP TABLE synergia.ai_assistances;
DROP FUNCTION synergia.ai_assistance_result_shape_valid(jsonb);
