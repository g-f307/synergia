DROP TABLE synergia.identity_access_events;
DROP TABLE synergia.session_refresh_tokens;
DROP TABLE synergia.identity_sessions;

DROP TRIGGER trg_identity_users_touch ON synergia.identity_users;
DROP TRIGGER trg_identity_users_audit ON synergia.identity_users;
DROP TRIGGER trg_identity_users_revoke_sessions ON synergia.identity_users;
DROP TRIGGER trg_identity_users_no_delete ON synergia.identity_users;
DROP TRIGGER trg_user_external_identities_no_delete
    ON synergia.user_external_identities;
DROP TRIGGER trg_user_emails_no_delete ON synergia.user_emails;
DROP TRIGGER trg_iam_organizations_no_delete ON synergia.iam_organizations;
DROP TRIGGER trg_identity_groups_no_delete ON synergia.identity_groups;
DROP TRIGGER trg_roles_no_delete ON synergia.roles;
DROP TRIGGER trg_permissions_no_delete ON synergia.permissions;

DROP FUNCTION synergia.prevent_identity_event_mutation();
DROP FUNCTION synergia.prevent_identity_hard_delete();
DROP FUNCTION synergia.revoke_sessions_for_inactive_user();
DROP FUNCTION synergia.after_identity_session_change();
DROP FUNCTION synergia.audit_identity_user();
DROP FUNCTION synergia.validate_identity_session();
DROP FUNCTION synergia.touch_identity_user();
