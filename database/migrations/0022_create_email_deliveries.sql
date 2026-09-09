CREATE TABLE synergia.email_notification_templates (
    notification_type text NOT NULL,
    template_version text NOT NULL,
    locale text NOT NULL CHECK (locale IN ('pt-BR', 'en-US')),
    subject_template text NOT NULL CHECK (btrim(subject_template) <> ''),
    body_template text NOT NULL CHECK (btrim(body_template) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (notification_type, template_version, locale),
    FOREIGN KEY (notification_type, template_version)
        REFERENCES synergia.notification_template_versions(
            notification_type, template_version
        )
);

INSERT INTO synergia.email_notification_templates (
    notification_type, template_version, locale,
    subject_template, body_template
)
SELECT notification_type, template_version, locale,
       title_template, body_template
FROM synergia.notification_templates;

CREATE TABLE synergia.email_deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    notification_id uuid NOT NULL REFERENCES synergia.notifications(id),
    notification_version integer NOT NULL CHECK (notification_version > 0),
    recipient_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    locale text NOT NULL CHECK (locale IN ('pt-BR', 'en-US')),
    template_version text NOT NULL CHECK (btrim(template_version) <> ''),
    state text NOT NULL CHECK (state IN (
        'queued', 'processing', 'retry', 'sent', 'skipped', 'failed'
    )),
    provider text NOT NULL CHECK (provider IN ('local_capture')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    claimed_at timestamptz,
    sent_at timestamptz,
    provider_reference text,
    failure_code text,
    correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (notification_id, notification_version)
);

CREATE INDEX idx_email_deliveries_ready
    ON synergia.email_deliveries (available_at, created_at, id)
    WHERE state IN ('queued', 'retry');
CREATE INDEX idx_email_deliveries_recipient
    ON synergia.email_deliveries (recipient_user_id, created_at DESC, id);

CREATE TABLE synergia.email_delivery_attempts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id uuid NOT NULL REFERENCES synergia.email_deliveries(id),
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    outcome text NOT NULL CHECK (outcome IN ('sent', 'retry', 'failed')),
    failure_code text,
    correlation_id uuid,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (delivery_id, attempt_number),
    CHECK ((outcome = 'sent' AND failure_code IS NULL)
        OR (outcome <> 'sent' AND failure_code IS NOT NULL))
);

CREATE INDEX idx_email_delivery_attempts_delivery
    ON synergia.email_delivery_attempts (delivery_id, occurred_at, id);

CREATE FUNCTION synergia.prevent_email_delivery_attempt_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'email_delivery_attempt_is_immutable' USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER email_delivery_attempts_immutable
BEFORE UPDATE OR DELETE ON synergia.email_delivery_attempts
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_email_delivery_attempt_mutation();

COMMENT ON TABLE synergia.email_deliveries IS
    'Estado operacional do canal de e-mail; endereços e credenciais não são persistidos';
COMMENT ON TABLE synergia.email_delivery_attempts IS
    'Auditoria append-only sem destinatário, corpo, token ou segredo de provedor';
COMMENT ON COLUMN synergia.email_deliveries.provider_reference IS
    'Referência técnica opaca; nunca contém credenciais ou conteúdo da mensagem';
