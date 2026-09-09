UPDATE synergia.permission_catalog_versions SET is_active = false WHERE is_active;

INSERT INTO synergia.permission_catalog_versions (version, description, is_active)
VALUES ('1.2.0', 'Permissões de notificações internas', true);

INSERT INTO synergia.permissions (
    permission_key, resource_type, description, catalog_version, is_reserved
) VALUES (
    'notification.read', 'notification',
    'Consultar e confirmar notificações internas próprias', '1.2.0', true
)
ON CONFLICT (normalized_key) DO NOTHING;

INSERT INTO synergia.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM synergia.roles r
JOIN synergia.permissions p ON p.normalized_key = 'notification.read'
WHERE r.normalized_key IN ('gestor', 'analista', 'operador', 'consulta')
ON CONFLICT (role_id, permission_id) WHERE revoked_at IS NULL DO NOTHING;

CREATE TABLE synergia.notification_template_versions (
    notification_type text NOT NULL,
    template_version text NOT NULL,
    required_permission text NOT NULL,
    resource_type text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (notification_type, template_version),
    CHECK (notification_type ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    CHECK (btrim(template_version) <> ''),
    CHECK (required_permission ~ '^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$'),
    CHECK (resource_type IN ('execution', 'pending', 'report'))
);

CREATE TABLE synergia.notification_templates (
    notification_type text NOT NULL,
    template_version text NOT NULL,
    locale text NOT NULL CHECK (locale IN ('pt-BR', 'en-US')),
    title_template text NOT NULL CHECK (btrim(title_template) <> ''),
    body_template text NOT NULL CHECK (btrim(body_template) <> ''),
    PRIMARY KEY (notification_type, template_version, locale),
    FOREIGN KEY (notification_type, template_version)
        REFERENCES synergia.notification_template_versions(
            notification_type, template_version
        )
);

INSERT INTO synergia.notification_template_versions (
    notification_type, template_version, required_permission, resource_type
) VALUES
    ('execution.completed', '1.0.0', 'execution.read', 'execution'),
    ('execution.completed_with_errors', '1.0.0', 'execution.read', 'execution'),
    ('execution.failed', '1.0.0', 'execution.read', 'execution'),
    ('pending.summary', '1.0.0', 'pending.read', 'pending'),
    ('report.succeeded', '1.0.0', 'report.read', 'report'),
    ('report.failed', '1.0.0', 'report.read', 'report'),
    ('report.cancelled', '1.0.0', 'report.read', 'report');

INSERT INTO synergia.notification_templates (
    notification_type, template_version, locale, title_template, body_template
) VALUES
    ('execution.completed', '1.0.0', 'pt-BR', 'Processamento concluído', 'A execução {execution_id} foi concluída.'),
    ('execution.completed', '1.0.0', 'en-US', 'Processing complete', 'Execution {execution_id} has completed.'),
    ('execution.completed_with_errors', '1.0.0', 'pt-BR', 'Processamento concluído com alertas', 'A execução {execution_id} foi concluída com erros.'),
    ('execution.completed_with_errors', '1.0.0', 'en-US', 'Processing completed with warnings', 'Execution {execution_id} completed with errors.'),
    ('execution.failed', '1.0.0', 'pt-BR', 'Falha no processamento', 'A execução {execution_id} não pôde ser concluída.'),
    ('execution.failed', '1.0.0', 'en-US', 'Processing failed', 'Execution {execution_id} could not be completed.'),
    ('pending.summary', '1.0.0', 'pt-BR', 'Pendências identificadas', 'A execução {execution_id} possui {count} pendência(s) aberta(s).'),
    ('pending.summary', '1.0.0', 'en-US', 'Pending items identified', 'Execution {execution_id} has {count} open pending item(s).'),
    ('report.succeeded', '1.0.0', 'pt-BR', 'Relatório disponível', 'A versão {version} do relatório está disponível.'),
    ('report.succeeded', '1.0.0', 'en-US', 'Report available', 'Report version {version} is available.'),
    ('report.failed', '1.0.0', 'pt-BR', 'Falha na geração do relatório', 'A versão {version} do relatório não pôde ser gerada.'),
    ('report.failed', '1.0.0', 'en-US', 'Report generation failed', 'Report version {version} could not be generated.'),
    ('report.cancelled', '1.0.0', 'pt-BR', 'Geração de relatório cancelada', 'A geração da versão {version} foi cancelada.'),
    ('report.cancelled', '1.0.0', 'en-US', 'Report generation cancelled', 'Generation of version {version} was cancelled.');

CREATE TABLE synergia.notifications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    notification_type text NOT NULL,
    template_version text NOT NULL,
    required_permission text NOT NULL,
    resource_type text NOT NULL CHECK (resource_type IN ('execution', 'pending', 'report')),
    resource_id text NOT NULL CHECK (btrim(resource_id) <> ''),
    parameters jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(parameters) = 'object'),
    aggregate_key text NOT NULL CHECK (btrim(aggregate_key) <> ''),
    state text NOT NULL CHECK (state IN ('unread', 'read', 'suppressed', 'failed')),
    occurrence_count integer NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    first_occurred_at timestamptz NOT NULL,
    last_occurred_at timestamptz NOT NULL,
    delivered_at timestamptz,
    read_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (notification_type, template_version)
        REFERENCES synergia.notification_template_versions(
            notification_type, template_version
        ),
    CHECK (last_occurred_at >= first_occurred_at),
    CHECK ((state = 'read' AND read_at IS NOT NULL) OR (state <> 'read' AND read_at IS NULL)),
    CHECK ((state IN ('unread', 'read') AND delivered_at IS NOT NULL)
        OR (state IN ('suppressed', 'failed') AND delivered_at IS NULL))
);

CREATE UNIQUE INDEX uq_notifications_unread_aggregate
    ON synergia.notifications (recipient_user_id, aggregate_key)
    WHERE state = 'unread';
CREATE INDEX idx_notifications_recipient_feed
    ON synergia.notifications (recipient_user_id, state, last_occurred_at DESC, id)
    WHERE state IN ('unread', 'read');
CREATE INDEX idx_notifications_recipient_unread
    ON synergia.notifications (recipient_user_id, last_occurred_at DESC)
    WHERE state = 'unread';

CREATE TABLE synergia.notification_occurrences (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    notification_id uuid REFERENCES synergia.notifications(id),
    recipient_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    source_kind text NOT NULL CHECK (source_kind IN ('audit_event', 'report_event')),
    source_event_id bigint NOT NULL,
    projection_key text NOT NULL CHECK (btrim(projection_key) <> ''),
    occurred_at timestamptz NOT NULL,
    UNIQUE (source_kind, source_event_id, recipient_user_id, projection_key)
);

CREATE TABLE synergia.notification_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    notification_id uuid REFERENCES synergia.notifications(id),
    recipient_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    event_type text NOT NULL CHECK (event_type IN (
        'notification.created', 'notification.delivered',
        'notification.consolidated', 'notification.suppressed',
        'notification.delivery_failed', 'notification.read'
    )),
    actor_user_id uuid REFERENCES synergia.identity_users(id),
    actor_session_id uuid REFERENCES synergia.identity_sessions(id),
    correlation_id uuid,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_notification_occurrences_notification
    ON synergia.notification_occurrences (notification_id, occurred_at, id);
CREATE INDEX idx_notification_events_notification
    ON synergia.notification_events (notification_id, occurred_at, id);
CREATE INDEX idx_notification_events_recipient
    ON synergia.notification_events (recipient_user_id, occurred_at DESC, id);

CREATE FUNCTION synergia.user_has_effective_permission(
    target_user_id uuid, target_permission text, target_organization_id uuid
) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT EXISTS (
        SELECT 1
        FROM synergia.user_role_assignments ura
        JOIN synergia.roles r ON r.id = ura.role_id AND r.is_active
        JOIN synergia.role_permissions rp ON rp.role_id = r.id AND rp.revoked_at IS NULL
        JOIN synergia.permissions p ON p.id = rp.permission_id AND p.is_active
        WHERE ura.user_id = target_user_id AND ura.revoked_at IS NULL
          AND (ura.expires_at IS NULL OR ura.expires_at > now())
          AND p.normalized_key = target_permission
          AND (ura.organization_id IS NULL OR ura.organization_id = target_organization_id)
        UNION ALL
        SELECT 1
        FROM synergia.user_group_memberships ugm
        JOIN synergia.identity_groups g ON g.id = ugm.group_id AND g.is_active
        JOIN synergia.group_role_assignments gra ON gra.group_id = g.id AND gra.revoked_at IS NULL
        JOIN synergia.roles r ON r.id = gra.role_id AND r.is_active
        JOIN synergia.role_permissions rp ON rp.role_id = r.id AND rp.revoked_at IS NULL
        JOIN synergia.permissions p ON p.id = rp.permission_id AND p.is_active
        WHERE ugm.user_id = target_user_id AND ugm.revoked_at IS NULL
          AND p.normalized_key = target_permission
          AND (gra.organization_id IS NULL OR gra.organization_id = target_organization_id)
        UNION ALL
        SELECT 1
        FROM synergia.user_permission_assignments upa
        JOIN synergia.permissions p ON p.id = upa.permission_id AND p.is_active
        WHERE upa.user_id = target_user_id AND upa.revoked_at IS NULL
          AND p.normalized_key = target_permission
          AND (upa.organization_id IS NULL OR upa.organization_id = target_organization_id)
    );
$$;

CREATE FUNCTION synergia.enqueue_internal_notification(
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
            target_correlation_id, jsonb_build_object('channel', 'in_app', 'reason', 'preference_disabled')
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
        last_occurred_at = GREATEST(synergia.notifications.last_occurred_at, EXCLUDED.last_occurred_at),
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

CREATE FUNCTION synergia.project_execution_notification()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    execution_row record;
    pending_count integer;
    recipient record;
    target_type text;
BEGIN
    IF NEW.event_type NOT IN ('execution_completed', 'execution_failed') THEN
        RETURN NEW;
    END IF;
    SELECT id, status, organization_id, initiated_by_user_id
      INTO execution_row FROM synergia.executions WHERE id = NEW.execution_id;
    IF execution_row.organization_id IS NULL THEN RETURN NEW; END IF;

    target_type := CASE
        WHEN execution_row.status = 'completed' THEN 'execution.completed'
        WHEN execution_row.status = 'completed_with_errors' THEN 'execution.completed_with_errors'
        ELSE 'execution.failed' END;
    IF execution_row.initiated_by_user_id IS NOT NULL THEN
        PERFORM synergia.enqueue_internal_notification(
            execution_row.initiated_by_user_id, execution_row.organization_id,
            target_type, execution_row.id,
            jsonb_build_object('execution_id', execution_row.id),
            target_type || ':' || execution_row.id,
            'audit_event', NEW.id, NEW.occurred_at
        );
    END IF;

    IF NEW.event_type = 'execution_completed' THEN
        SELECT count(*) INTO pending_count FROM synergia.pending_items
        WHERE execution_id = execution_row.id AND status = 'open';
        IF pending_count > 0 THEN
            FOR recipient IN
                SELECT u.id FROM synergia.identity_users u
                WHERE u.status = 'active'
                  AND synergia.user_has_effective_permission(
                      u.id, 'pending.read', execution_row.organization_id
                  )
                  AND synergia.user_has_effective_permission(
                      u.id, 'notification.read', execution_row.organization_id
                  )
            LOOP
                PERFORM synergia.enqueue_internal_notification(
                    recipient.id, execution_row.organization_id, 'pending.summary',
                    execution_row.id,
                    jsonb_build_object('execution_id', execution_row.id, 'count', pending_count),
                    'pending.summary:' || execution_row.id,
                    'audit_event', NEW.id, NEW.occurred_at
                );
            END LOOP;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION synergia.project_report_notification()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE report_row record; target_type text;
BEGIN
    IF NEW.event_type NOT IN (
        'report.generation_succeeded', 'report.generation_failed',
        'report.generation_cancelled'
    ) THEN RETURN NEW; END IF;
    SELECT rv.id, rv.report_id, rv.version, rv.organization_id,
           rv.requested_by_user_id
      INTO report_row
    FROM synergia.report_versions rv WHERE rv.id = NEW.report_version_id;
    target_type := CASE NEW.event_type
        WHEN 'report.generation_succeeded' THEN 'report.succeeded'
        WHEN 'report.generation_failed' THEN 'report.failed'
        ELSE 'report.cancelled' END;
    PERFORM synergia.enqueue_internal_notification(
        report_row.requested_by_user_id, report_row.organization_id,
        target_type, report_row.report_id::text,
        jsonb_build_object('version', report_row.version),
        target_type || ':' || report_row.id::text,
        'report_event', NEW.id, NEW.occurred_at, NEW.correlation_id
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER audit_events_project_notification
AFTER INSERT ON synergia.audit_events
FOR EACH ROW EXECUTE FUNCTION synergia.project_execution_notification();

CREATE TRIGGER report_events_project_notification
AFTER INSERT ON synergia.report_events
FOR EACH ROW EXECUTE FUNCTION synergia.project_report_notification();

CREATE FUNCTION synergia.prevent_notification_audit_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'notification_audit_is_immutable' USING ERRCODE = '23514';
END;
$$;

CREATE FUNCTION synergia.restrict_notification_occurrence_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.notification_id IS NULL AND NEW.notification_id IS NOT NULL
       AND OLD.recipient_user_id = NEW.recipient_user_id
       AND OLD.source_kind = NEW.source_kind
       AND OLD.source_event_id = NEW.source_event_id
       AND OLD.projection_key = NEW.projection_key
       AND OLD.occurred_at = NEW.occurred_at THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'notification_occurrence_is_immutable' USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER notification_occurrences_immutable
BEFORE UPDATE OR DELETE ON synergia.notification_occurrences
FOR EACH ROW EXECUTE FUNCTION synergia.restrict_notification_occurrence_mutation();
CREATE TRIGGER notification_events_immutable
BEFORE UPDATE OR DELETE ON synergia.notification_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_notification_audit_mutation();

COMMENT ON TABLE synergia.notifications IS
    'Caixa interna do destinatário; não representa entrega por canal externo';
COMMENT ON COLUMN synergia.notifications.parameters IS
    'Somente parâmetros mínimos permitidos para renderização; nunca conteúdo fonte';
COMMENT ON TABLE synergia.notification_events IS
    'Auditoria append-only de criação, entrega interna, consolidação, leitura e falha';
