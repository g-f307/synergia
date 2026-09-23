CREATE TABLE synergia.notification_event_policies (
    notification_type text PRIMARY KEY,
    required_permission text NOT NULL,
    resource_type text NOT NULL,
    allowed_placeholders text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (notification_type ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    CHECK (required_permission ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    CHECK (resource_type IN ('execution', 'pending', 'report', 'approval'))
);

INSERT INTO synergia.notification_event_policies (
    notification_type, required_permission, resource_type, allowed_placeholders
)
SELECT DISTINCT ON (notification_type)
       notification_type, required_permission, resource_type,
       CASE
         WHEN notification_type LIKE 'execution.%' THEN ARRAY['execution_id']::text[]
         WHEN notification_type = 'pending.summary' THEN ARRAY['execution_id', 'count']::text[]
         WHEN notification_type LIKE 'report.%' THEN ARRAY['version']::text[]
         WHEN notification_type LIKE 'approval.%' THEN ARRAY['pending_id']::text[]
         ELSE ARRAY[]::text[]
       END
FROM synergia.notification_template_versions
ORDER BY notification_type, created_at DESC;

CREATE TABLE synergia.notification_template_revisions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_type text NOT NULL
        REFERENCES synergia.notification_event_policies(notification_type),
    channel text NOT NULL CHECK (channel IN ('in_app', 'email')),
    locale text NOT NULL CHECK (locale IN ('pt-BR', 'en-US')),
    version_number integer NOT NULL CHECK (version_number > 0),
    version_label text NOT NULL CHECK (btrim(version_label) <> ''),
    title_template text NOT NULL CHECK (btrim(title_template) <> ''),
    body_template text NOT NULL CHECK (btrim(body_template) <> ''),
    row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
    created_by_user_id uuid REFERENCES synergia.identity_users(id),
    created_reason text NOT NULL CHECK (btrim(created_reason) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_by_user_id uuid REFERENCES synergia.identity_users(id),
    updated_reason text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    published_by_user_id uuid REFERENCES synergia.identity_users(id),
    published_reason text,
    published_at timestamptz,
    UNIQUE (notification_type, channel, locale, version_number),
    UNIQUE (notification_type, channel, locale, version_label),
    CHECK (
      (published_at IS NULL AND published_by_user_id IS NULL AND published_reason IS NULL)
      OR
      (published_at IS NOT NULL AND published_reason IS NOT NULL)
    )
);

INSERT INTO synergia.notification_template_revisions (
    notification_type, channel, locale, version_number, version_label,
    title_template, body_template, created_reason, published_reason,
    published_at
)
SELECT t.notification_type, 'in_app', t.locale,
       dense_rank() OVER (
         PARTITION BY t.notification_type, t.locale
         ORDER BY v.created_at, t.template_version
       ),
       t.template_version, t.title_template, t.body_template,
       'Migração do catálogo inicial', 'Versão inicial homologada', now()
FROM synergia.notification_templates t
JOIN synergia.notification_template_versions v
  ON v.notification_type = t.notification_type
 AND v.template_version = t.template_version;

INSERT INTO synergia.notification_template_revisions (
    notification_type, channel, locale, version_number, version_label,
    title_template, body_template, created_reason, published_reason,
    published_at
)
SELECT t.notification_type, 'email', t.locale,
       dense_rank() OVER (
         PARTITION BY t.notification_type, t.locale
         ORDER BY v.created_at, t.template_version
       ),
       t.template_version, t.subject_template, t.body_template,
       'Migração do catálogo inicial', 'Versão inicial homologada', now()
FROM synergia.email_notification_templates t
JOIN synergia.notification_template_versions v
  ON v.notification_type = t.notification_type
 AND v.template_version = t.template_version;

CREATE TABLE synergia.notification_template_activations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id uuid NOT NULL
        REFERENCES synergia.notification_template_revisions(id),
    notification_type text NOT NULL,
    channel text NOT NULL CHECK (channel IN ('in_app', 'email')),
    locale text NOT NULL CHECK (locale IN ('pt-BR', 'en-US')),
    activated_by_user_id uuid REFERENCES synergia.identity_users(id),
    activated_reason text NOT NULL CHECK (btrim(activated_reason) <> ''),
    activated_at timestamptz NOT NULL DEFAULT now(),
    deactivated_by_user_id uuid REFERENCES synergia.identity_users(id),
    deactivated_reason text,
    deactivated_at timestamptz,
    CHECK (
      (deactivated_at IS NULL AND deactivated_by_user_id IS NULL AND deactivated_reason IS NULL)
      OR
      (deactivated_at IS NOT NULL AND deactivated_reason IS NOT NULL)
    )
);

CREATE UNIQUE INDEX uq_notification_template_active
    ON synergia.notification_template_activations (
      notification_type, channel, locale
    ) WHERE deactivated_at IS NULL;

CREATE INDEX idx_notification_template_history
    ON synergia.notification_template_revisions (
      notification_type, channel, locale, version_number DESC
    );

CREATE UNIQUE INDEX uq_notification_template_version_label_after_seed
    ON synergia.notification_template_revisions (
      notification_type, channel, version_number
    ) WHERE created_by_user_id IS NOT NULL;

INSERT INTO synergia.notification_template_activations (
    revision_id, notification_type, channel, locale, activated_reason
)
SELECT DISTINCT ON (notification_type, channel, locale)
       id, notification_type, channel, locale, 'Versão inicial homologada'
FROM synergia.notification_template_revisions
ORDER BY notification_type, channel, locale,
         version_number DESC, version_label DESC, id DESC;

CREATE TABLE synergia.notification_template_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    revision_id uuid NOT NULL
        REFERENCES synergia.notification_template_revisions(id),
    event_type text NOT NULL CHECK (event_type IN (
      'template.draft_created', 'template.draft_updated',
      'template.published', 'template.deactivated'
    )),
    actor_user_id uuid REFERENCES synergia.identity_users(id),
    actor_session_id uuid REFERENCES synergia.identity_sessions(id),
    correlation_id uuid,
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(payload) = 'object'),
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_notification_template_events_revision
    ON synergia.notification_template_events (revision_id, occurred_at, id);

INSERT INTO synergia.notification_template_events (
    revision_id, event_type, reason, payload
)
SELECT id, 'template.published', 'Versão inicial homologada',
       jsonb_build_object('version', version_number, 'migration', true)
FROM synergia.notification_template_revisions;

ALTER TABLE synergia.notifications
    ADD COLUMN template_revision_id uuid
        REFERENCES synergia.notification_template_revisions(id),
    ADD COLUMN template_locale text CHECK (template_locale IN ('pt-BR', 'en-US')),
    ADD COLUMN email_template_revision_id uuid
        REFERENCES synergia.notification_template_revisions(id),
    ADD COLUMN email_template_locale text
        CHECK (email_template_locale IN ('pt-BR', 'en-US'));

UPDATE synergia.notifications n
SET (template_revision_id, template_locale) = (
    SELECT r.id, r.locale
    FROM synergia.notification_template_revisions r
    JOIN synergia.identity_users u ON u.id = n.recipient_user_id
    WHERE r.notification_type = n.notification_type
      AND r.channel = 'in_app'
      AND r.version_label = n.template_version
    ORDER BY CASE
      WHEN r.locale = CASE WHEN u.locale = 'en-US' THEN 'en-US' ELSE 'pt-BR' END THEN 0
      WHEN r.locale = 'pt-BR' THEN 1 ELSE 2 END
    LIMIT 1
);

UPDATE synergia.notifications n
SET (email_template_revision_id, email_template_locale) = (
    SELECT r.id, r.locale
    FROM synergia.notification_template_revisions r
    JOIN synergia.identity_users u ON u.id = n.recipient_user_id
    WHERE r.notification_type = n.notification_type
      AND r.channel = 'email'
      AND r.version_label = n.template_version
    ORDER BY CASE
      WHEN r.locale = CASE WHEN u.locale = 'en-US' THEN 'en-US' ELSE 'pt-BR' END THEN 0
      WHEN r.locale = 'pt-BR' THEN 1 ELSE 2 END
    LIMIT 1
);

ALTER TABLE synergia.notifications
    ALTER COLUMN template_revision_id SET NOT NULL,
    ALTER COLUMN template_locale SET NOT NULL;

ALTER TABLE synergia.email_deliveries
    ADD COLUMN template_revision_id uuid
        REFERENCES synergia.notification_template_revisions(id);

UPDATE synergia.email_deliveries d
SET template_revision_id = n.email_template_revision_id
FROM synergia.notifications n
WHERE n.id = d.notification_id;

CREATE FUNCTION synergia.prevent_published_notification_template_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'notification_template_deletion_forbidden'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.published_at IS NOT NULL THEN
        RAISE EXCEPTION 'published_notification_template_is_immutable'
            USING ERRCODE = '55000';
    END IF;
    IF NEW.published_at IS NOT NULL AND ROW(
        OLD.notification_type, OLD.channel, OLD.locale, OLD.version_number,
        OLD.version_label, OLD.title_template, OLD.body_template,
        OLD.created_by_user_id, OLD.created_reason, OLD.created_at
      ) IS DISTINCT FROM ROW(
        NEW.notification_type, NEW.channel, NEW.locale, NEW.version_number,
        NEW.version_label, NEW.title_template, NEW.body_template,
        NEW.created_by_user_id, NEW.created_reason, NEW.created_at
      ) THEN
        RAISE EXCEPTION 'notification_template_publish_must_not_edit_content'
            USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER notification_template_revision_immutable
BEFORE UPDATE OR DELETE ON synergia.notification_template_revisions
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_published_notification_template_mutation();

CREATE FUNCTION synergia.restrict_notification_template_activation_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.deactivated_at IS NULL AND NEW.deactivated_at IS NOT NULL
       AND ROW(OLD.revision_id, OLD.notification_type, OLD.channel, OLD.locale,
               OLD.activated_by_user_id, OLD.activated_reason, OLD.activated_at)
           IS NOT DISTINCT FROM
           ROW(NEW.revision_id, NEW.notification_type, NEW.channel, NEW.locale,
               NEW.activated_by_user_id, NEW.activated_reason, NEW.activated_at)
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'notification_template_activation_is_immutable'
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER notification_template_activation_immutable
BEFORE UPDATE OR DELETE ON synergia.notification_template_activations
FOR EACH ROW EXECUTE FUNCTION synergia.restrict_notification_template_activation_mutation();

CREATE TRIGGER notification_template_events_immutable
BEFORE UPDATE OR DELETE ON synergia.notification_template_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_notification_audit_mutation();

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
    target_locale text;
    internal_revision record;
    email_revision record;
    preference_enabled boolean;
    resulting_count integer;
    inserted_occurrence_id bigint;
    effective_aggregate_key text;
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

    SELECT p.required_permission, p.resource_type,
           CASE WHEN u.locale = 'en-US' THEN 'en-US' ELSE 'pt-BR' END
      INTO target_permission, target_resource_type, target_locale
    FROM synergia.notification_event_policies p
    JOIN synergia.identity_users u ON u.id = target_user_id
    WHERE p.notification_type = target_type;

    SELECT r.* INTO internal_revision
    FROM synergia.notification_template_activations a
    JOIN synergia.notification_template_revisions r ON r.id = a.revision_id
    WHERE a.notification_type = target_type AND a.channel = 'in_app'
      AND a.deactivated_at IS NULL
    ORDER BY CASE WHEN r.locale = target_locale THEN 0
                  WHEN r.locale = 'pt-BR' THEN 1 ELSE 2 END
    LIMIT 1;

    IF internal_revision.id IS NULL THEN
        INSERT INTO synergia.notification_events (
            recipient_user_id, event_type, correlation_id, payload
        ) VALUES (
            target_user_id, 'notification.delivery_failed', target_correlation_id,
            jsonb_build_object('channel', 'in_app', 'code', 'template_unavailable')
        );
        RETURN NULL;
    END IF;

    SELECT r.* INTO email_revision
    FROM synergia.notification_template_activations a
    JOIN synergia.notification_template_revisions r ON r.id = a.revision_id
    WHERE a.notification_type = target_type AND a.channel = 'email'
      AND a.deactivated_at IS NULL
    ORDER BY CASE WHEN r.locale = target_locale THEN 0
                  WHEN r.locale = 'pt-BR' THEN 1 ELSE 2 END
    LIMIT 1;

    SELECT status = 'active'
           AND COALESCE((notification_preferences->>'in_app')::boolean, true)
      INTO preference_enabled
    FROM synergia.identity_users WHERE id = target_user_id;

    effective_aggregate_key := target_aggregate_key || ':template:' || internal_revision.id::text;

    IF NOT COALESCE(preference_enabled, false) THEN
        INSERT INTO synergia.notifications (
            recipient_user_id, organization_id, notification_type,
            template_version, template_revision_id, template_locale,
            email_template_revision_id, email_template_locale,
            required_permission, resource_type, resource_id,
            parameters, aggregate_key, state, first_occurred_at,
            last_occurred_at
        ) VALUES (
            target_user_id, target_organization_id, target_type,
            internal_revision.version_label, internal_revision.id,
            internal_revision.locale, email_revision.id, email_revision.locale,
            target_permission, target_resource_type, target_resource_id,
            target_parameters, effective_aggregate_key, 'suppressed',
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
            jsonb_build_object('channel', 'in_app', 'reason', 'preference_disabled')
        );
        RETURN target_notification_id;
    END IF;

    INSERT INTO synergia.notifications (
        recipient_user_id, organization_id, notification_type,
        template_version, template_revision_id, template_locale,
        email_template_revision_id, email_template_locale,
        required_permission, resource_type, resource_id,
        parameters, aggregate_key, state, first_occurred_at,
        last_occurred_at, delivered_at
    ) VALUES (
        target_user_id, target_organization_id, target_type,
        internal_revision.version_label, internal_revision.id,
        internal_revision.locale, email_revision.id, email_revision.locale,
        target_permission, target_resource_type, target_resource_id,
        target_parameters, effective_aggregate_key, 'unread', target_occurred_at,
        target_occurred_at, now()
    ) ON CONFLICT (recipient_user_id, aggregate_key) WHERE state = 'unread'
      DO UPDATE SET
        parameters = EXCLUDED.parameters,
        occurrence_count = synergia.notifications.occurrence_count + 1,
        last_occurred_at = GREATEST(
          synergia.notifications.last_occurred_at, EXCLUDED.last_occurred_at
        ),
        updated_at = now(), version = synergia.notifications.version + 1
    RETURNING id, occurrence_count INTO target_notification_id, resulting_count;

    UPDATE synergia.notification_occurrences SET notification_id = target_notification_id
    WHERE source_kind = target_source_kind AND source_event_id = target_source_event_id
      AND recipient_user_id = target_user_id AND projection_key = target_aggregate_key;

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

COMMENT ON TABLE synergia.notification_event_policies IS
    'Catálogo técnico de eventos, autorização e placeholders permitidos';
COMMENT ON TABLE synergia.notification_template_revisions IS
    'Conteúdo versionado por evento, canal e idioma; publicação torna-o imutável';
COMMENT ON TABLE synergia.notification_template_activations IS
    'Histórico da política de versão ativa por evento, canal e idioma';
COMMENT ON TABLE synergia.notification_template_events IS
    'Auditoria append-only das transições administrativas de templates';
