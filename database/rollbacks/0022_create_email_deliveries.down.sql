DROP TRIGGER IF EXISTS email_delivery_attempts_immutable
    ON synergia.email_delivery_attempts;
DROP TABLE IF EXISTS synergia.email_delivery_attempts;
DROP FUNCTION IF EXISTS synergia.prevent_email_delivery_attempt_mutation();
DROP TABLE IF EXISTS synergia.email_deliveries;
DROP TABLE IF EXISTS synergia.email_notification_templates;
