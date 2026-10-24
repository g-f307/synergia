ALTER TABLE synergia.email_deliveries
    DROP CONSTRAINT email_deliveries_provider_check,
    ADD CONSTRAINT email_deliveries_provider_check
        CHECK (provider IN ('local_capture', 'smtp'));

CREATE TABLE synergia.email_delivery_reconciliations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id uuid NOT NULL REFERENCES synergia.email_deliveries(id),
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    request_id uuid NOT NULL UNIQUE,
    resolution text NOT NULL CHECK (resolution IN ('accepted', 'not_accepted')),
    evidence text NOT NULL CHECK (evidence IN ('smtp_log', 'recipient_confirmation')),
    actor_identifier text NOT NULL
        CHECK (actor_identifier ~ '^[A-Za-z0-9_-]{3,128}$'),
    resulting_state text NOT NULL CHECK (resulting_state IN ('sent', 'retry', 'failed')),
    correlation_id uuid NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (delivery_id, attempt_number),
    CHECK (resolution = 'accepted' OR evidence = 'smtp_log')
);

CREATE FUNCTION synergia.prevent_email_reconciliation_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'email_reconciliation_is_immutable' USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER email_reconciliations_immutable
BEFORE UPDATE OR DELETE ON synergia.email_delivery_reconciliations
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_email_reconciliation_mutation();

COMMENT ON TABLE synergia.email_delivery_reconciliations IS
    'Reconciliação explícita append-only; sem destinatário, conteúdo ou resposta SMTP';
