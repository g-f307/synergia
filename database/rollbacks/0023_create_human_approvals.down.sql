DROP TRIGGER IF EXISTS trg_approval_events_immutable ON synergia.approval_events;
DROP FUNCTION IF EXISTS synergia.prevent_approval_event_mutation();
DROP TABLE IF EXISTS synergia.approval_events;
DROP TABLE IF EXISTS synergia.approval_stages;
DROP TABLE IF EXISTS synergia.approval_requests;
DROP TRIGGER IF EXISTS approval_policy_activation_events_immutable
    ON synergia.approval_policy_activation_events;
DROP TABLE IF EXISTS synergia.approval_policy_activation_events;
DROP TRIGGER IF EXISTS approval_policies_audit_activation
    ON synergia.approval_policies;
DROP FUNCTION IF EXISTS synergia.audit_approval_policy_activation();
DROP TRIGGER IF EXISTS approval_policies_published_immutable
    ON synergia.approval_policies;
DROP FUNCTION IF EXISTS synergia.prevent_published_approval_policy_mutation();
DROP TABLE IF EXISTS synergia.approval_policies;
ALTER TABLE synergia.email_delivery_attempts
    DISABLE TRIGGER email_delivery_attempts_immutable;
ALTER TABLE synergia.notification_events
    DISABLE TRIGGER notification_events_immutable;
ALTER TABLE synergia.notification_occurrences
    DISABLE TRIGGER notification_occurrences_immutable;
DELETE FROM synergia.email_delivery_attempts
WHERE delivery_id IN (
    SELECT ed.id FROM synergia.email_deliveries ed
    JOIN synergia.notifications n ON n.id = ed.notification_id
    WHERE n.notification_type LIKE 'approval.%'
);
DELETE FROM synergia.email_deliveries
WHERE notification_id IN (
    SELECT id FROM synergia.notifications WHERE notification_type LIKE 'approval.%'
);
DELETE FROM synergia.notification_events
WHERE notification_id IN (
    SELECT id FROM synergia.notifications WHERE notification_type LIKE 'approval.%'
);
DELETE FROM synergia.notification_occurrences
WHERE notification_id IN (
    SELECT id FROM synergia.notifications WHERE notification_type LIKE 'approval.%'
);
ALTER TABLE synergia.notification_occurrences
    ENABLE TRIGGER notification_occurrences_immutable;
ALTER TABLE synergia.notification_events
    ENABLE TRIGGER notification_events_immutable;
ALTER TABLE synergia.email_delivery_attempts
    ENABLE TRIGGER email_delivery_attempts_immutable;
DELETE FROM synergia.notifications WHERE notification_type LIKE 'approval.%';
DELETE FROM synergia.notification_templates WHERE notification_type LIKE 'approval.%';
DELETE FROM synergia.notification_template_versions WHERE notification_type LIKE 'approval.%';
ALTER TABLE synergia.notifications DROP CONSTRAINT notifications_resource_type_check;
ALTER TABLE synergia.notifications ADD CONSTRAINT notifications_resource_type_check
    CHECK (resource_type IN ('execution', 'pending', 'report'));
ALTER TABLE synergia.notification_template_versions
    DROP CONSTRAINT notification_template_versions_resource_type_check;
ALTER TABLE synergia.notification_template_versions
    ADD CONSTRAINT notification_template_versions_resource_type_check
    CHECK (resource_type IN ('execution', 'pending', 'report'));
DELETE FROM synergia.role_permissions
WHERE permission_id IN (
    SELECT id FROM synergia.permissions WHERE normalized_key LIKE 'approval.%'
);
DELETE FROM synergia.user_permission_assignments
WHERE permission_id IN (
    SELECT id FROM synergia.permissions WHERE normalized_key LIKE 'approval.%'
);
ALTER TABLE synergia.permissions DISABLE TRIGGER trg_permissions_no_delete;
DELETE FROM synergia.permissions WHERE normalized_key LIKE 'approval.%';
ALTER TABLE synergia.permissions ENABLE TRIGGER trg_permissions_no_delete;
UPDATE synergia.permission_catalog_versions SET is_active = false WHERE version = '1.3.0';
UPDATE synergia.permission_catalog_versions SET is_active = true WHERE version = '1.2.0';
DELETE FROM synergia.permission_catalog_versions WHERE version = '1.3.0';
