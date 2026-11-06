-- Manual, approved downgrade only; stop API/collector first. Preserve delivery
-- evidence and LLM history. Never replay accepted records after a downgrade.
DO $$
DECLARE source text;
BEGIN
    FOREACH source IN ARRAY ARRAY['audit_events', 'identity_access_events',
        'report_events', 'approval_events', 'notification_events',
        'notification_template_events', 'data_operation_events',
        'approval_policy_activation_events', 'email_delivery_attempts',
        'email_delivery_reconciliations', 'audit_export_events',
        'observability_events', 'rate_limit_events']
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS graylog_source_insert ON synergia.%I', source);
    END LOOP;
END $$;
DROP FUNCTION synergia.enqueue_graylog_source();
DROP VIEW synergia.audit_event_catalog;
ALTER VIEW synergia.audit_event_catalog_v1 RENAME TO audit_event_catalog;
-- All tables deliberately retained for investigation/recovery.
