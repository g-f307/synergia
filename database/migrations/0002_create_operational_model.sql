CREATE TABLE synergia.executions (
    id text PRIMARY KEY,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed', 'cancelled')),
    attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
    reprocessed_from_id text REFERENCES synergia.executions(id),
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (reprocessed_from_id IS NULL OR reprocessed_from_id <> id),
    CHECK (finished_at IS NULL OR finished_at >= started_at),
    UNIQUE (reprocessed_from_id, attempt)
);

CREATE TABLE synergia.source_files (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    file_name text NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-fA-F]{64}$'),
    media_type text,
    size_bytes bigint CHECK (size_bytes IS NULL OR size_bytes >= 0),
    imported_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (content_hash),
    UNIQUE (execution_id, file_name)
);

CREATE TABLE synergia.organizations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    organization_code text NOT NULL,
    organization_name text,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (organization_code)
);

CREATE TABLE synergia.workorders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workorder_number text NOT NULL,
    organization_id bigint REFERENCES synergia.organizations(id),
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    processing_status text NOT NULL DEFAULT 'pending'
        CHECK (processing_status IN ('pending', 'validated', 'consolidated', 'failed')),
    planned_quantity integer NOT NULL DEFAULT 0 CHECK (planned_quantity >= 0),
    produced_quantity integer NOT NULL DEFAULT 0 CHECK (produced_quantity >= 0),
    received_quantity integer NOT NULL DEFAULT 0 CHECK (received_quantity >= 0),
    released_quantity integer NOT NULL DEFAULT 0 CHECK (released_quantity >= 0),
    pending_quantity integer NOT NULL DEFAULT 0 CHECK (pending_quantity >= 0),
    retained_quantity integer NOT NULL DEFAULT 0 CHECK (retained_quantity >= 0),
    partially_released boolean NOT NULL DEFAULT false,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (execution_id, workorder_number),
    CHECK (released_quantity <= received_quantity),
    CHECK (NOT partially_released OR (released_quantity > 0 AND released_quantity < received_quantity))
);

CREATE TABLE synergia.lots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lot_number text NOT NULL,
    workorder_id bigint NOT NULL REFERENCES synergia.workorders(id),
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workorder_id, lot_number)
);

CREATE TABLE synergia.serials (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    serial_number text NOT NULL,
    container_number text,
    workorder_id bigint NOT NULL REFERENCES synergia.workorders(id),
    lot_id bigint REFERENCES synergia.lots(id),
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (serial_number),
    UNIQUE NULLS NOT DISTINCT (container_number, serial_number)
);

CREATE TABLE synergia.holds (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    serial_id bigint REFERENCES synergia.serials(id),
    workorder_id bigint NOT NULL REFERENCES synergia.workorders(id),
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    reason text,
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'released', 'cancelled')),
    post_release boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (post_release)
);

CREATE TABLE synergia.oqc_decisions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workorder_id bigint NOT NULL REFERENCES synergia.workorders(id),
    lot_id bigint REFERENCES synergia.lots(id),
    serial_id bigint REFERENCES synergia.serials(id),
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    decision_state text NOT NULL
        CHECK (decision_state IN ('pending', 'approved', 'partially_approved', 'rejected', 'not_applicable')),
    reason text,
    decided_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE synergia.pending_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    workorder_id bigint NOT NULL REFERENCES synergia.workorders(id),
    lot_id bigint REFERENCES synergia.lots(id),
    serial_id bigint REFERENCES synergia.serials(id),
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint NOT NULL REFERENCES synergia.source_files(id),
    category text NOT NULL,
    reason text,
    status text NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'resolved', 'cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE synergia.audit_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    execution_id text NOT NULL REFERENCES synergia.executions(id),
    source_file_id bigint REFERENCES synergia.source_files(id),
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_executions_reprocessed_from ON synergia.executions (reprocessed_from_id);
CREATE INDEX idx_source_files_execution ON synergia.source_files (execution_id);
CREATE INDEX idx_workorders_number ON synergia.workorders (workorder_number);
CREATE INDEX idx_workorders_execution ON synergia.workorders (execution_id);
CREATE INDEX idx_lots_number ON synergia.lots (lot_number);
CREATE INDEX idx_lots_execution ON synergia.lots (execution_id);
CREATE INDEX idx_serials_number ON synergia.serials (serial_number);
CREATE INDEX idx_serials_workorder ON synergia.serials (workorder_id);
CREATE INDEX idx_serials_execution ON synergia.serials (execution_id);
CREATE INDEX idx_holds_execution ON synergia.holds (execution_id);
CREATE INDEX idx_oqc_decisions_execution ON synergia.oqc_decisions (execution_id);
CREATE INDEX idx_pending_items_execution ON synergia.pending_items (execution_id);
CREATE INDEX idx_audit_events_execution ON synergia.audit_events (execution_id);
