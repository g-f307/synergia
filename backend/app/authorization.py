from __future__ import annotations

from uuid import UUID


def global_admins_cte() -> str:
    return """
    WITH effective_admins AS (
        SELECT ura.user_id
        FROM synergia.user_role_assignments ura
        JOIN synergia.roles r ON r.id = ura.role_id AND r.is_active
        WHERE ura.revoked_at IS NULL
          AND ura.organization_id IS NULL
          AND (ura.expires_at IS NULL OR ura.expires_at > now())
          AND r.normalized_key = 'admin'
        UNION
        SELECT ugm.user_id
        FROM synergia.user_group_memberships ugm
        JOIN synergia.identity_groups g ON g.id = ugm.group_id AND g.is_active
        JOIN synergia.group_role_assignments gra
          ON gra.group_id = g.id AND gra.revoked_at IS NULL
        JOIN synergia.roles r ON r.id = gra.role_id AND r.is_active
        WHERE ugm.revoked_at IS NULL
          AND gra.organization_id IS NULL
          AND r.normalized_key = 'admin'
        UNION
        SELECT upa.user_id
        FROM synergia.user_permission_assignments upa
        JOIN synergia.permissions p
          ON p.id = upa.permission_id AND p.is_active
        WHERE upa.revoked_at IS NULL
          AND upa.organization_id IS NULL
          AND p.normalized_key = 'access.admin'
        UNION
        SELECT ura.user_id
        FROM synergia.user_role_assignments ura
        JOIN synergia.roles r ON r.id = ura.role_id AND r.is_active
        JOIN synergia.role_permissions rp
          ON rp.role_id = r.id AND rp.revoked_at IS NULL
        JOIN synergia.permissions p
          ON p.id = rp.permission_id AND p.is_active
        WHERE ura.revoked_at IS NULL
          AND ura.organization_id IS NULL
          AND (ura.expires_at IS NULL OR ura.expires_at > now())
          AND p.normalized_key = 'access.admin'
        UNION
        SELECT ugm.user_id
        FROM synergia.user_group_memberships ugm
        JOIN synergia.identity_groups g ON g.id = ugm.group_id AND g.is_active
        JOIN synergia.group_role_assignments gra
          ON gra.group_id = g.id AND gra.revoked_at IS NULL
        JOIN synergia.roles r ON r.id = gra.role_id AND r.is_active
        JOIN synergia.role_permissions rp
          ON rp.role_id = r.id AND rp.revoked_at IS NULL
        JOIN synergia.permissions p
          ON p.id = rp.permission_id AND p.is_active
        WHERE ugm.revoked_at IS NULL
          AND gra.organization_id IS NULL
          AND p.normalized_key = 'access.admin'
    )
    """


def is_global_admin(cursor, user_id: UUID) -> bool:
    cursor.execute(
        global_admins_cte()
        + """
        SELECT EXISTS (
            SELECT 1
            FROM effective_admins ea
            JOIN synergia.identity_users u ON u.id = ea.user_id
            WHERE ea.user_id = %s AND u.status = 'active'
        ) AS authorized
        """,
        (user_id,),
    )
    return cursor.fetchone()["authorized"]


def active_global_admin_count(cursor) -> int:
    cursor.execute(
        global_admins_cte()
        + """
        SELECT count(DISTINCT ea.user_id) AS total
        FROM effective_admins ea
        JOIN synergia.identity_users u ON u.id = ea.user_id
        WHERE u.status = 'active'
        """
    )
    return cursor.fetchone()["total"]
