import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';

import { environment } from '../../../environments/environment';
import {
  AdminAssociation, AdminGroup, AdminOrganization, AdminPage, AdminPermission, AdminRole, AdminUser,
  AssociationChangeResponse, AssociationKind, EffectivePermission, UserEmail, UserFilters, UserStatus
} from './admin.models';

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/admin`;

  users(page: number, pageSize: number, filters: UserFilters) {
    return this.http.get<AdminPage<AdminUser>>(`${this.base}/users`, {
      params: this.params({ page, page_size: pageSize, ...filters })
    });
  }
  user(id: string) { return this.http.get<AdminUser>(`${this.base}/users/${encodeURIComponent(id)}`); }
  createUser(payload: { display_name: string; status: 'pending' | 'active'; emails: UserEmail[]; reason: string }) {
    return this.http.post<AdminUser>(`${this.base}/users`, payload);
  }
  updateUser(id: string, payload: { version: number; display_name: string; emails: UserEmail[]; reason: string }) {
    return this.http.patch<AdminUser>(`${this.base}/users/${encodeURIComponent(id)}`, payload);
  }
  changeUserStatus(id: string, action: 'block' | 'unblock' | 'deactivate' | 'reactivate', version: number, reason: string) {
    return this.http.post<AdminUser>(`${this.base}/users/${encodeURIComponent(id)}/${action}`, { version, reason });
  }

  groups(page: number, pageSize = 25) {
    return this.http.get<AdminPage<AdminGroup>>(`${this.base}/access/groups`, { params: this.params({ page, page_size: pageSize }) });
  }
  group(id: string) { return this.http.get<AdminGroup>(`${this.base}/access/groups/${encodeURIComponent(id)}`); }
  createGroup(payload: { group_name: string; external_reference: string | null; reason: string }) {
    return this.http.post<AdminGroup>(`${this.base}/access/groups`, payload);
  }
  updateGroup(id: string, payload: { version: number; group_name: string; external_reference: string | null; reason: string }) {
    return this.http.patch<AdminGroup>(`${this.base}/access/groups/${encodeURIComponent(id)}`, payload);
  }
  changeGroupStatus(id: string, action: 'activate' | 'deactivate', version: number, reason: string) {
    return this.http.post<AdminGroup>(`${this.base}/access/groups/${encodeURIComponent(id)}/${action}`, { version, reason });
  }

  roles(page: number, pageSize = 25) {
    return this.http.get<AdminPage<AdminRole>>(`${this.base}/access/roles`, { params: this.params({ page, page_size: pageSize }) });
  }
  role(id: string) { return this.http.get<AdminRole>(`${this.base}/access/roles/${encodeURIComponent(id)}`); }
  createRole(payload: { role_key: string; description: string | null; reason: string }) {
    return this.http.post<AdminRole>(`${this.base}/access/roles`, payload);
  }
  updateRole(id: string, payload: { version: number; description: string; reason: string }) {
    return this.http.patch<AdminRole>(`${this.base}/access/roles/${encodeURIComponent(id)}`, payload);
  }
  changeRoleStatus(id: string, action: 'activate' | 'deactivate', version: number, reason: string) {
    return this.http.post<AdminRole>(`${this.base}/access/roles/${encodeURIComponent(id)}/${action}`, { version, reason });
  }

  permissions() { return this.http.get<AdminPermission[]>(`${this.base}/access/permissions`); }
  organizations(page: number, query = '', pageSize = 25) {
    return this.http.get<AdminPage<AdminOrganization>>(`${this.base}/access/organizations`, {
      params: this.params({ page, page_size: pageSize, query })
    });
  }
  associations(
    kind: AssociationKind, page: number, pageSize = 25,
    filters: { left_id?: string; right_id?: string; organization_id?: string; active_only?: boolean } = {}
  ) {
    return this.http.get<AdminPage<AdminAssociation>>(`${this.base}/access/associations`, {
      params: this.params({ kind, page, page_size: pageSize, ...filters })
    });
  }
  grant(kind: AssociationKind, leftId: string, rightId: string, reason: string, organizationId?: string) {
    return this.http.put<AssociationChangeResponse>(this.associationPath(kind, leftId, rightId), {
      reason, ...(organizationId ? { organization_id: organizationId } : {})
    });
  }
  revoke(kind: AssociationKind, leftId: string, rightId: string, reason: string, organizationId?: string) {
    return this.http.delete<AssociationChangeResponse>(this.associationPath(kind, leftId, rightId), {
      body: { reason, ...(organizationId ? { organization_id: organizationId } : {}) }
    });
  }
  effectivePermissions(userId: string, organizationId?: string) {
    return this.http.get<{ user_id: string; permissions: EffectivePermission[] }>(
      `${this.base}/access/users/${encodeURIComponent(userId)}/effective-permissions`,
      { params: this.params({ organization_id: organizationId }) }
    );
  }

  private params(values: Record<string, string | number | boolean | UserStatus | undefined>): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(values)) {
      if (value !== undefined && value !== '') params = params.set(key, String(value));
    }
    return params;
  }
  private associationPath(kind: AssociationKind, leftId: string, rightId: string): string {
    const segments: Record<AssociationKind, readonly [string, string]> = {
      user_group: ['users', 'groups'], user_role: ['users', 'roles'],
      group_role: ['groups', 'roles'], role_permission: ['roles', 'permissions'],
      user_permission: ['users', 'permissions']
    };
    const [left, right] = segments[kind];
    return `${this.base}/access/${left}/${encodeURIComponent(leftId)}/${right}/${encodeURIComponent(rightId)}`;
  }
}
