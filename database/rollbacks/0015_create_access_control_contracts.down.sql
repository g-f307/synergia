DROP TABLE synergia.user_permission_assignments;
DROP TABLE synergia.group_role_assignments;

DROP INDEX synergia.uq_role_permissions_active;
DELETE FROM synergia.role_permissions rp
USING synergia.roles r
WHERE rp.role_id = r.id
  AND (NOT rp.preexisting_in_0015 OR NOT r.preexisting_in_0015);
ALTER TABLE synergia.role_permissions DROP CONSTRAINT role_permissions_pkey;
ALTER TABLE synergia.role_permissions
    DROP COLUMN id,
    DROP COLUMN revoked_at,
    DROP COLUMN revocation_reason,
    DROP COLUMN preexisting_in_0015;
ALTER TABLE synergia.role_permissions
    ADD PRIMARY KEY (role_id, permission_id);

DROP TRIGGER trg_roles_touch ON synergia.roles;
DROP TRIGGER trg_identity_groups_touch ON synergia.identity_groups;
DROP FUNCTION synergia.touch_versioned_access_entity();

DELETE FROM synergia.user_role_assignments ura
USING synergia.roles r
WHERE ura.role_id = r.id AND NOT r.preexisting_in_0015;
ALTER TABLE synergia.roles DISABLE TRIGGER trg_roles_no_delete;
DELETE FROM synergia.roles WHERE NOT preexisting_in_0015;
ALTER TABLE synergia.roles ENABLE TRIGGER trg_roles_no_delete;
ALTER TABLE synergia.roles
    DROP COLUMN preexisting_in_0015,
    DROP COLUMN version;
ALTER TABLE synergia.identity_groups DROP COLUMN version;
ALTER TABLE synergia.permissions DISABLE TRIGGER trg_permissions_no_delete;
DELETE FROM synergia.permissions WHERE NOT preexisting_in_0015;
ALTER TABLE synergia.permissions ENABLE TRIGGER trg_permissions_no_delete;
ALTER TABLE synergia.permissions
    DROP CONSTRAINT permissions_normalized_key_check,
    DROP COLUMN is_reserved,
    DROP COLUMN catalog_version,
    DROP COLUMN preexisting_in_0015,
    ADD CHECK (
        normalized_key ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'
    );

DROP TABLE synergia.permission_catalog_versions;
