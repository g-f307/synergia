UPDATE synergia.permission_catalog_versions SET is_active = false WHERE is_active;

INSERT INTO synergia.permission_catalog_versions (version, description, is_active)
VALUES ('1.1.0', 'Permissões de geração e consulta de relatórios', true);

INSERT INTO synergia.permissions (
    permission_key, resource_type, description, catalog_version, is_reserved
) VALUES
    ('report.generate', 'report', 'Gerar versões persistentes de relatórios', '1.1.0', true),
    ('report.read', 'report', 'Consultar catálogo, histórico e dados de relatórios', '1.1.0', true)
ON CONFLICT (normalized_key) DO NOTHING;

INSERT INTO synergia.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM synergia.roles r
JOIN synergia.permissions p ON p.normalized_key IN ('report.generate', 'report.read')
WHERE
    (r.normalized_key = 'gestor')
    OR (r.normalized_key = 'analista' AND p.normalized_key = 'report.read')
    OR (r.normalized_key = 'consulta' AND p.normalized_key = 'report.read')
ON CONFLICT (role_id, permission_id) WHERE revoked_at IS NULL DO NOTHING;

CREATE TABLE synergia.reports (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type text NOT NULL CHECK (
        report_type IN ('workorder_consolidated', 'oqc_summary')
    ),
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    created_by_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, organization_id)
);

ALTER TABLE synergia.executions
    ADD CONSTRAINT executions_id_organization_key UNIQUE (id, organization_id);

CREATE TABLE synergia.report_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    execution_id text NOT NULL,
    organization_id uuid NOT NULL REFERENCES synergia.iam_organizations(id),
    requested_by_user_id uuid NOT NULL REFERENCES synergia.identity_users(id),
    requested_by_session_id uuid REFERENCES synergia.identity_sessions(id),
    reference_at timestamptz NOT NULL,
    filters jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(filters) = 'object'),
    schema_version text NOT NULL CHECK (btrim(schema_version) <> ''),
    state text NOT NULL CHECK (state IN ('generating', 'succeeded', 'failed', 'cancelled')),
    completeness text CHECK (completeness IN ('complete', 'partial')),
    failure_code text,
    failure_message text,
    correlation_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (report_id, version),
    UNIQUE (id, report_id),
    FOREIGN KEY (report_id, organization_id)
        REFERENCES synergia.reports(id, organization_id),
    FOREIGN KEY (execution_id, organization_id)
        REFERENCES synergia.executions(id, organization_id),
    CHECK (completed_at IS NULL OR completed_at >= created_at),
    CHECK (
        (state = 'generating' AND completed_at IS NULL AND failure_code IS NULL)
        OR (state = 'succeeded' AND completed_at IS NOT NULL AND failure_code IS NULL)
        OR (state = 'failed' AND completed_at IS NOT NULL AND failure_code IS NOT NULL)
        OR (state = 'cancelled' AND completed_at IS NOT NULL)
    )
);

CREATE TABLE synergia.report_artifacts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_version_id uuid NOT NULL REFERENCES synergia.report_versions(id),
    artifact_type text NOT NULL CHECK (artifact_type IN ('data')),
    media_type text NOT NULL DEFAULT 'application/json',
    content jsonb NOT NULL,
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (report_version_id, artifact_type),
    CHECK (jsonb_typeof(content) = 'object')
);

CREATE TABLE synergia.report_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    report_version_id uuid NOT NULL REFERENCES synergia.report_versions(id),
    event_type text NOT NULL CHECK (event_type IN (
        'report.generation_started', 'report.generation_succeeded',
        'report.generation_failed', 'report.generation_cancelled',
        'report.consulted'
    )),
    actor_user_id uuid REFERENCES synergia.identity_users(id),
    correlation_id uuid,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    occurred_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_reports_organization_catalog
    ON synergia.reports (organization_id, created_at DESC, id);
CREATE INDEX idx_report_versions_execution
    ON synergia.report_versions (execution_id, created_at DESC);
CREATE INDEX idx_report_versions_catalog
    ON synergia.report_versions (report_id, version DESC);
CREATE INDEX idx_report_versions_organization
    ON synergia.report_versions (organization_id, created_at DESC);
CREATE INDEX idx_report_events_version_time
    ON synergia.report_events (report_version_id, occurred_at, id);

CREATE FUNCTION synergia.prevent_report_catalog_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'report_catalog_is_immutable' USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER reports_immutable
BEFORE UPDATE OR DELETE ON synergia.reports
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_report_catalog_mutation();

CREATE FUNCTION synergia.prevent_report_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'report_history_is_immutable' USING ERRCODE = '23514';
    END IF;
    IF OLD.report_id IS DISTINCT FROM NEW.report_id
       OR OLD.version IS DISTINCT FROM NEW.version
       OR OLD.execution_id IS DISTINCT FROM NEW.execution_id
       OR OLD.organization_id IS DISTINCT FROM NEW.organization_id
       OR OLD.requested_by_user_id IS DISTINCT FROM NEW.requested_by_user_id
       OR OLD.requested_by_session_id IS DISTINCT FROM NEW.requested_by_session_id
       OR OLD.reference_at IS DISTINCT FROM NEW.reference_at
       OR OLD.filters IS DISTINCT FROM NEW.filters
       OR OLD.schema_version IS DISTINCT FROM NEW.schema_version
       OR OLD.completeness IS DISTINCT FROM NEW.completeness
       OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
        RAISE EXCEPTION 'report_version_is_immutable' USING ERRCODE = '23514';
    END IF;
    IF OLD.state <> 'generating' OR NEW.state NOT IN ('succeeded', 'failed', 'cancelled') THEN
        RAISE EXCEPTION 'invalid_report_transition:%->%', OLD.state, NEW.state
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER report_versions_immutable
BEFORE UPDATE OR DELETE ON synergia.report_versions
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_report_history_mutation();

CREATE FUNCTION synergia.prevent_report_artifact_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'report_artifact_is_immutable' USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER report_artifacts_immutable
BEFORE UPDATE OR DELETE ON synergia.report_artifacts
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_report_artifact_mutation();

CREATE FUNCTION synergia.prevent_report_event_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'report_event_is_immutable' USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER report_events_immutable
BEFORE UPDATE OR DELETE ON synergia.report_events
FOR EACH ROW EXECUTE FUNCTION synergia.prevent_report_event_mutation();

COMMENT ON TABLE synergia.reports IS
    'Identidade estável de um relatório; novas gerações criam versões';
COMMENT ON TABLE synergia.report_versions IS
    'Contexto reproduzível e imutável de cada geração, inclusive falhas';
COMMENT ON TABLE synergia.report_artifacts IS
    'Snapshot gerado exclusivamente dos dados persistidos da execução';
COMMENT ON COLUMN synergia.report_versions.completeness IS
    'partial identifica explicitamente execução completed_with_errors';
