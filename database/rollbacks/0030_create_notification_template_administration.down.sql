DROP TRIGGER IF EXISTS notification_template_events_immutable
    ON synergia.notification_template_events;
DROP TRIGGER IF EXISTS notification_template_activation_immutable
    ON synergia.notification_template_activations;
DROP TRIGGER IF EXISTS notification_template_revision_immutable
    ON synergia.notification_template_revisions;

ALTER TABLE IF EXISTS synergia.email_deliveries
    DROP COLUMN IF EXISTS template_revision_id;
ALTER TABLE synergia.notifications
    DROP COLUMN IF EXISTS email_template_locale,
    DROP COLUMN IF EXISTS email_template_revision_id,
    DROP COLUMN IF EXISTS template_locale,
    DROP COLUMN IF EXISTS template_revision_id;

DROP TABLE IF EXISTS synergia.notification_template_events;
DROP TABLE IF EXISTS synergia.notification_template_activations;
DROP TABLE IF EXISTS synergia.notification_template_revisions;
DROP TABLE IF EXISTS synergia.notification_event_policies;
DROP FUNCTION IF EXISTS synergia.restrict_notification_template_activation_mutation();
DROP FUNCTION IF EXISTS synergia.prevent_published_notification_template_mutation();

CREATE OR REPLACE FUNCTION synergia.enqueue_internal_notification(
    target_user_id uuid, target_organization_id uuid,
    target_type text, target_resource_id text, target_parameters jsonb,
    target_aggregate_key text, target_source_kind text,
    target_source_event_id bigint, target_occurred_at timestamptz,
    target_correlation_id uuid DEFAULT NULL
) RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE
    target_notification_id uuid;
    target_permission text;
    target_resource_type text;
    preference_enabled boolean;
    resulting_count integer;
    inserted_occurrence_id bigint;
BEGIN
    INSERT INTO synergia.notification_occurrences (
        recipient_user_id, source_kind, source_event_id, projection_key, occurred_at
    ) VALUES (
        target_user_id, target_source_kind, target_source_event_id,
        target_aggregate_key, target_occurred_at
    ) ON CONFLICT DO NOTHING RETURNING id INTO inserted_occurrence_id;
    IF inserted_occurrence_id IS NULL THEN
        RETURN NULL;
    END IF;

    SELECT required_permission, resource_type
      INTO target_permission, target_resource_type
    FROM synergia.notification_template_versions
    WHERE notification_type = target_type AND template_version = '1.0.0';

    SELECT status = 'active'
           AND COALESCE((notification_preferences->>'in_app')::boolean, true)
      INTO preference_enabled
    FROM synergia.identity_users WHERE id = target_user_id;

    IF NOT COALESCE(preference_enabled, false) THEN
        INSERT INTO synergia.notifications (
            recipient_user_id, organization_id, notification_type,
            template_version, required_permission, resource_type, resource_id,
            parameters, aggregate_key, state, first_occurred_at,
            last_occurred_at
        ) VALUES (
            target_user_id, target_organization_id, target_type, '1.0.0',
            target_permission, target_resource_type, target_resource_id,
            target_parameters, target_aggregate_key, 'suppressed',
            target_occurred_at, target_occurred_at
        ) RETURNING id INTO target_notification_id;
        UPDATE synergia.notification_occurrences
           SET notification_id = target_notification_id
         WHERE source_kind = target_source_kind
           AND source_event_id = target_source_event_id
           AND recipient_user_id = target_user_id
           AND projection_key = target_aggregate_key;
        INSERT INTO synergia.notification_events (
            notification_id, recipient_user_id, event_type, correlation_id, payload
        ) VALUES (
            target_notification_id, target_user_id, 'notification.suppressed',
            target_correlation_id,
            jsonb_build_object(
                'channel', 'in_app', 'reason', 'preference_disabled'
            )
        );
        RETURN target_notification_id;
    END IF;

    INSERT INTO synergia.notifications (
        recipient_user_id, organization_id, notification_type,
        template_version, required_permission, resource_type, resource_id,
        parameters, aggregate_key, state, first_occurred_at,
        last_occurred_at, delivered_at
    ) VALUES (
        target_user_id, target_organization_id, target_type, '1.0.0',
        target_permission, target_resource_type, target_resource_id,
        target_parameters, target_aggregate_key, 'unread', target_occurred_at,
        target_occurred_at, now()
    ) ON CONFLICT (recipient_user_id, aggregate_key) WHERE state = 'unread'
      DO UPDATE SET
        parameters = EXCLUDED.parameters,
        occurrence_count = synergia.notifications.occurrence_count + 1,
        last_occurred_at = GREATEST(
            synergia.notifications.last_occurred_at,
            EXCLUDED.last_occurred_at
        ),
        updated_at = now(), version = synergia.notifications.version + 1
    RETURNING id, occurrence_count INTO target_notification_id, resulting_count;

    UPDATE synergia.notification_occurrences
       SET notification_id = target_notification_id
     WHERE source_kind = target_source_kind
       AND source_event_id = target_source_event_id
       AND recipient_user_id = target_user_id
       AND projection_key = target_aggregate_key;

    INSERT INTO synergia.notification_events (
        notification_id, recipient_user_id, event_type, correlation_id, payload
    ) VALUES (
        target_notification_id, target_user_id,
        CASE WHEN resulting_count = 1 THEN 'notification.created'
             ELSE 'notification.consolidated' END,
        target_correlation_id,
        jsonb_build_object('channel', 'in_app', 'occurrence_count', resulting_count)
    );
    IF resulting_count = 1 THEN
        INSERT INTO synergia.notification_events (
            notification_id, recipient_user_id, event_type, correlation_id, payload
        ) VALUES (
            target_notification_id, target_user_id, 'notification.delivered',
            target_correlation_id, jsonb_build_object('channel', 'in_app')
        );
    END IF;
    RETURN target_notification_id;
EXCEPTION WHEN OTHERS THEN
    INSERT INTO synergia.notification_events (
        recipient_user_id, event_type, correlation_id, payload
    ) VALUES (
        target_user_id, 'notification.delivery_failed', target_correlation_id,
        jsonb_build_object('channel', 'in_app', 'code', 'projection_failed')
    );
    RETURN NULL;
END;
$$;
