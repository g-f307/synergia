DROP TABLE synergia.user_permission_assignments;
DROP TABLE synergia.group_role_assignments;

DROP INDEX synergia.uq_role_permissions_active;
DELETE FROM synergia.role_permissions;
ALTER TABLE synergia.role_permissions DROP CONSTRAINT role_permissions_pkey;
ALTER TABLE synergia.role_permissions
    DROP COLUMN id,
    DROP COLUMN revoked_at,
    DROP COLUMN revocation_reason,
    ADD PRIMARY KEY (role_id, permission_id);

DROP TRIGGER trg_roles_touch ON synergia.roles;
DROP TRIGGER trg_identity_groups_touch ON synergia.identity_groups;
DROP FUNCTION synergia.touch_versioned_access_entity();

ALTER TABLE synergia.roles DROP COLUMN version;
ALTER TABLE synergia.identity_groups DROP COLUMN version;
DELETE FROM synergia.permissions WHERE catalog_version = '1.0.0';
ALTER TABLE synergia.permissions
    DROP CONSTRAINT permissions_normalized_key_check,
    DROP COLUMN is_reserved,
    DROP COLUMN catalog_version,
    ADD CHECK (
        normalized_key ~ '^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$'
    );

DROP TABLE synergia.permission_catalog_versions;
