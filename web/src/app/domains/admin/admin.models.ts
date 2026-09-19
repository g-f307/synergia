export interface AdminPage<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
  sort: string;
}

export type UserStatus = 'pending' | 'active' | 'blocked' | 'inactive';

export interface UserEmail {
  email: string;
  is_primary: boolean;
  is_verified: boolean;
}

export interface AdminUser {
  id: string;
  display_name: string;
  status: UserStatus;
  emails: UserEmail[];
  version: number;
  created_at: string;
  updated_at: string;
  deactivated_at: string | null;
  last_login_at: string | null;
}

export interface AdminGroup {
  id: string;
  group_name: string;
  external_reference: string | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  deactivated_at: string | null;
}

export interface AdminRole {
  id: string;
  role_key: string;
  description: string | null;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  deactivated_at: string | null;
}

export interface UserFilters {
  name?: string;
  email?: string;
  status?: UserStatus;
  group?: string;
  role?: string;
  organization?: string;
}

export interface AdminPermission {
  id: string;
  permission_key: string;
  resource_type: string;
  description: string | null;
  catalog_version: string;
  is_reserved: boolean;
  is_active: boolean;
}

export interface AdminOrganization {
  id: string;
  organization_code: string;
  display_name: string;
}

export type AssociationKind = 'user_group' | 'user_role' | 'group_role' | 'role_permission' | 'user_permission';

export interface AdminAssociation {
  id: string;
  kind: AssociationKind;
  left_id: string;
  right_id: string;
  organization_id: string | null;
  granted_at: string;
  revoked_at: string | null;
}

export interface AssociationChangeResponse {
  id: string | null;
  idempotent: boolean;
  kind: AssociationKind;
}

export interface EffectivePermission {
  permission_key: string;
  resource_type: string;
  source: 'direct' | 'role' | 'group';
  source_id: string;
  organization_id: string | null;
  organization_code: string | null;
}
