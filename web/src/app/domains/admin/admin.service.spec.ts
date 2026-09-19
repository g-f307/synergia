import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { AdminService } from './admin.service';

describe('AdminService', () => {
  let service: AdminService;
  let http: HttpTestingController;
  const base = `${environment.apiUrl}/admin`;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(AdminService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('uses the server-side user filters and pagination', () => {
    service.users(2, 25, { name: 'Ana', email: 'ana@example.invalid', status: 'active', group: 'quality', role: 'gestor', organization: 'org-a' }).subscribe();
    const request = http.expectOne((item) => item.url === `${base}/users`);
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('name')).toBe('Ana');
    expect(request.request.params.get('email')).toBe('ana@example.invalid');
    expect(request.request.params.get('group')).toBe('quality');
    expect(request.request.params.get('role')).toBe('gestor');
    expect(request.request.params.get('organization')).toBe('org-a');
    request.flush({ items: [], page: 2, page_size: 25, total: 0, pages: 0, sort: 'created_at,id' });
  });

  it('sends only allowed user fields and the optimistic version', () => {
    service.updateUser('user-1', { version: 4, display_name: 'Ana', emails: [{ email: 'ana@example.invalid', is_primary: true, is_verified: false }], reason: 'name correction' }).subscribe();
    const request = http.expectOne(`${base}/users/user-1`);
    expect(request.request.method).toBe('PATCH');
    expect(Object.keys(request.request.body).sort()).toEqual(['display_name', 'emails', 'reason', 'version']);
    expect(request.request.body.version).toBe(4);
    request.flush({});
  });

  it('loads filtered associations and the authenticated organization catalog', () => {
    service.associations('user_role', 3, 25, { left_id: 'user-1', organization_id: 'org-1', active_only: true }).subscribe();
    const associations = http.expectOne((item) => item.url === `${base}/access/associations`);
    expect(associations.request.params.get('kind')).toBe('user_role');
    expect(associations.request.params.get('left_id')).toBe('user-1');
    expect(associations.request.params.get('organization_id')).toBe('org-1');
    expect(associations.request.params.get('active_only')).toBe('true');
    associations.flush({ items: [], page: 3, page_size: 25, total: 0, pages: 0, sort: 'granted_at,kind,id' });
    service.organizations(2, 'north').subscribe();
    const organizations = http.expectOne((item) => item.url === `${base}/access/organizations`);
    expect(organizations.request.params.get('query')).toBe('north');
    expect(organizations.request.params.get('page')).toBe('2');
    organizations.flush({ items: [], page: 2, page_size: 25, total: 0, pages: 0, sort: 'organization_code,id' });
  });

  it('preserves justification and organization on grant and revoke', () => {
    service.grant('group_role', 'group-1', 'role-2', 'approved scope', 'org-3').subscribe();
    const grant = http.expectOne(`${base}/access/groups/group-1/roles/role-2`);
    expect(grant.request.method).toBe('PUT');
    expect(grant.request.body).toEqual({ reason: 'approved scope', organization_id: 'org-3' });
    grant.flush({ id: 'link-1', idempotent: false, kind: 'group_role' });
    service.revoke('group_role', 'group-1', 'role-2', 'access removed', 'org-3').subscribe();
    const revoke = http.expectOne(`${base}/access/groups/group-1/roles/role-2`);
    expect(revoke.request.method).toBe('DELETE');
    expect(revoke.request.body).toEqual({ reason: 'access removed', organization_id: 'org-3' });
    revoke.flush({ id: 'link-1', idempotent: false, kind: 'group_role' });
  });
});
