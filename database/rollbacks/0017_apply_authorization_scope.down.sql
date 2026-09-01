DROP INDEX IF EXISTS synergia.idx_identity_events_correlation;
DROP INDEX IF EXISTS synergia.idx_executions_authorization_scope;
ALTER TABLE synergia.identity_access_events DROP COLUMN correlation_id;
ALTER TABLE synergia.executions
    DROP COLUMN initiated_by_session_id,
    DROP COLUMN initiated_by_user_id,
    DROP COLUMN organization_id;
