ALTER TABLE synergia.executions
    ADD COLUMN organization_id uuid REFERENCES synergia.iam_organizations(id),
    ADD COLUMN initiated_by_user_id uuid REFERENCES synergia.identity_users(id),
    ADD COLUMN initiated_by_session_id uuid REFERENCES synergia.identity_sessions(id);

ALTER TABLE synergia.identity_access_events
    ADD COLUMN correlation_id uuid;

CREATE INDEX idx_executions_authorization_scope
    ON synergia.executions (organization_id, started_at DESC, id);

CREATE INDEX idx_identity_events_correlation
    ON synergia.identity_access_events (correlation_id)
    WHERE correlation_id IS NOT NULL;

COMMENT ON COLUMN synergia.executions.organization_id IS
    'Escopo IAM imutavel da execucao; registros legados nulos exigem classificacao';
COMMENT ON COLUMN synergia.identity_access_events.correlation_id IS
    'Identificador tecnico da requisicao, sem credenciais ou dados pessoais';
