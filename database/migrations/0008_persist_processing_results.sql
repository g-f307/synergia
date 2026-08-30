ALTER TABLE synergia.source_files
    ADD CONSTRAINT source_files_id_execution_key UNIQUE (id, execution_id);

ALTER TABLE synergia.organizations
    DROP CONSTRAINT organizations_organization_code_key,
    ADD CONSTRAINT organizations_execution_code_key
        UNIQUE (execution_id, organization_code),
    ADD CONSTRAINT organizations_id_execution_key UNIQUE (id, execution_id),
    ADD CONSTRAINT organizations_source_execution_fk
        FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id);

ALTER TABLE synergia.workorders
    ALTER COLUMN planned_quantity DROP NOT NULL,
    ALTER COLUMN planned_quantity DROP DEFAULT,
    ALTER COLUMN produced_quantity DROP NOT NULL,
    ALTER COLUMN produced_quantity DROP DEFAULT,
    ALTER COLUMN received_quantity DROP NOT NULL,
    ALTER COLUMN received_quantity DROP DEFAULT,
    ALTER COLUMN released_quantity DROP NOT NULL,
    ALTER COLUMN released_quantity DROP DEFAULT,
    ALTER COLUMN pending_quantity DROP NOT NULL,
    ALTER COLUMN pending_quantity DROP DEFAULT,
    ALTER COLUMN retained_quantity DROP NOT NULL,
    ALTER COLUMN retained_quantity DROP DEFAULT,
    ALTER COLUMN partially_released DROP NOT NULL,
    ALTER COLUMN partially_released DROP DEFAULT,
    ADD CONSTRAINT workorders_id_execution_key UNIQUE (id, execution_id),
    ADD CONSTRAINT workorders_source_execution_fk
        FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id),
    ADD CONSTRAINT workorders_organization_execution_fk
        FOREIGN KEY (organization_id, execution_id)
        REFERENCES synergia.organizations(id, execution_id);

ALTER TABLE synergia.lots
    ADD CONSTRAINT lots_id_workorder_execution_key
        UNIQUE (id, workorder_id, execution_id),
    ADD CONSTRAINT lots_workorder_execution_fk
        FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    ADD CONSTRAINT lots_source_execution_fk
        FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id);

ALTER TABLE synergia.serials
    DROP CONSTRAINT serials_serial_number_key,
    DROP CONSTRAINT serials_container_number_serial_number_key,
    ADD CONSTRAINT serials_execution_number_key
        UNIQUE (execution_id, serial_number),
    ADD CONSTRAINT serials_execution_container_number_key
        UNIQUE NULLS NOT DISTINCT (execution_id, container_number, serial_number),
    ADD CONSTRAINT serials_id_workorder_lot_execution_key
        UNIQUE NULLS NOT DISTINCT (id, workorder_id, lot_id, execution_id),
    ADD CONSTRAINT serials_workorder_execution_fk
        FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    ADD CONSTRAINT serials_lot_workorder_execution_fk
        FOREIGN KEY (lot_id, workorder_id, execution_id)
        REFERENCES synergia.lots(id, workorder_id, execution_id),
    ADD CONSTRAINT serials_source_execution_fk
        FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id);

CREATE TABLE synergia.classifications (
    classification_id text PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    workorder_id bigint NOT NULL,
    lot_id bigint,
    serial_id bigint,
    source_file_id bigint NOT NULL,
    rule_id text NOT NULL,
    rule_catalog_version text NOT NULL,
    state text NOT NULL CHECK (state IN ('active', 'closed')),
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    justification text NOT NULL,
    reason text,
    data_quality text NOT NULL CHECK (data_quality IN ('complete', 'partial')),
    priority text NOT NULL,
    priority_score integer NOT NULL,
    responsible_area text,
    occurred_at timestamptz,
    classified_at timestamptz NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (classification_id, execution_id, workorder_id),
    FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    FOREIGN KEY (lot_id, workorder_id, execution_id)
        REFERENCES synergia.lots(id, workorder_id, execution_id),
    FOREIGN KEY (serial_id, workorder_id, lot_id, execution_id)
        REFERENCES synergia.serials(id, workorder_id, lot_id, execution_id),
    FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id),
    CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE TABLE synergia.rule_evaluations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    workorder_id bigint NOT NULL,
    source_file_id bigint,
    rule_id text NOT NULL,
    rule_catalog_version text NOT NULL,
    result text NOT NULL CHECK (result IN ('matched', 'not_matched')),
    justification text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id),
    CHECK (jsonb_typeof(evidence) = 'object')
);

CREATE TABLE synergia.consolidated_field_provenance (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    workorder_id bigint NOT NULL,
    source_file_id bigint NOT NULL,
    field_name text NOT NULL,
    source text NOT NULL,
    sheet_name text,
    row_number integer,
    observed_value jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id)
);

ALTER TABLE synergia.holds
    ADD COLUMN classification_id text REFERENCES synergia.classifications(classification_id),
    ADD CONSTRAINT holds_workorder_execution_fk
        FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    ADD CONSTRAINT holds_source_execution_fk
        FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id);

ALTER TABLE synergia.oqc_decisions
    ADD COLUMN classification_id text REFERENCES synergia.classifications(classification_id),
    ADD CONSTRAINT oqc_workorder_execution_fk
        FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    ADD CONSTRAINT oqc_source_execution_fk
        FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id);

ALTER TABLE synergia.pending_items
    ADD COLUMN classification_id text REFERENCES synergia.classifications(classification_id),
    ADD COLUMN rule_id text,
    ADD COLUMN rule_catalog_version text,
    ADD COLUMN priority text,
    ADD COLUMN priority_score integer,
    ADD COLUMN responsible_area text,
    ADD COLUMN evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD CONSTRAINT pending_workorder_execution_fk
        FOREIGN KEY (workorder_id, execution_id)
        REFERENCES synergia.workorders(id, execution_id),
    ADD CONSTRAINT pending_source_execution_fk
        FOREIGN KEY (source_file_id, execution_id)
        REFERENCES synergia.source_files(id, execution_id),
    ADD CONSTRAINT pending_evidence_object_check
        CHECK (jsonb_typeof(evidence) = 'object');

CREATE INDEX idx_classifications_execution_rule
    ON synergia.classifications (execution_id, rule_id, state);
CREATE INDEX idx_classifications_workorder
    ON synergia.classifications (workorder_id, classified_at);
CREATE INDEX idx_rule_evaluations_execution_rule
    ON synergia.rule_evaluations (execution_id, rule_id, result);
CREATE INDEX idx_provenance_workorder_field
    ON synergia.consolidated_field_provenance (workorder_id, field_name);
CREATE INDEX idx_pending_items_priority
    ON synergia.pending_items (status, priority_score DESC, created_at);
