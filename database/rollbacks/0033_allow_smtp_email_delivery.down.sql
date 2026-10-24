DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM synergia.email_deliveries WHERE provider = 'smtp')
        OR EXISTS (SELECT 1 FROM synergia.email_delivery_reconciliations)
    THEN
        RAISE EXCEPTION 'SMTP deliveries or reconciliation history prevent rollback';
    END IF;
END;
$$;

DROP TABLE synergia.email_delivery_reconciliations;
DROP FUNCTION synergia.prevent_email_reconciliation_mutation();
ALTER TABLE synergia.email_deliveries
    DROP CONSTRAINT email_deliveries_provider_check,
    ADD CONSTRAINT email_deliveries_provider_check CHECK (provider IN ('local_capture'));
