import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { AdminAssociationPanelComponent } from './admin-association-panel.component';
import { AdminAssociation } from './admin.models';
import { AdminService } from './admin.service';

describe('AdminAssociationPanelComponent', () => {
  const link: AdminAssociation = { id: 'link-1', kind: 'user_role', left_id: 'user-1', right_id: 'role-1', organization_id: 'org-1', granted_at: '', revoked_at: null };
  const page = (items: object[]) => ({ items, page: 1, page_size: 25, total: items.length, pages: 1, sort: 'granted_at,kind,id' });

  function setup(items: object[] = []) {
    const api = {
      associations: jasmine.createSpy().and.returnValue(of(page(items))),
      roles: jasmine.createSpy().and.returnValue(of(page([{ id: 'role-1', role_key: 'gestor', is_active: true }]))),
      role: jasmine.createSpy().and.returnValue(of({ id: 'role-1', role_key: 'gestor' })),
      organizations: jasmine.createSpy().and.returnValue(of(page([{ id: 'org-1', organization_code: 'north', display_name: 'North' }]))),
      grant: jasmine.createSpy().and.returnValue(of({ id: 'link-1', idempotent: false, kind: 'user_role' })),
      revoke: jasmine.createSpy().and.returnValue(of({ id: 'link-1', idempotent: false, kind: 'user_role' }))
    };
    TestBed.configureTestingModule({ imports: [AdminAssociationPanelComponent], providers: [provideRouter([]), { provide: AdminService, useValue: api }] });
    const fixture = TestBed.createComponent(AdminAssociationPanelComponent);
    fixture.componentRef.setInput('kind', 'user_role');
    fixture.componentRef.setInput('side', 'left');
    fixture.componentRef.setInput('entityId', 'user-1');
    fixture.componentRef.setInput('target', 'role');
    fixture.componentRef.setInput('titleKey', 'adminUi.userRoles');
    fixture.detectChanges();
    return { api, fixture, component: fixture.componentInstance };
  }

  it('requires an explicit organization before a scoped grant', () => {
    const { api, component } = setup();
    component.selectedTarget = 'role-1'; component.reason = 'approved assignment'; component.scope = 'organization';
    component.grant(new Event('submit'));
    expect(api.grant).not.toHaveBeenCalled();
    expect(component.formError()).toBe('adminUi.associationRequired');
    component.selectedOrganization = 'org-1'; component.grant(new Event('submit'));
    expect(api.grant).toHaveBeenCalledWith('user_role', 'user-1', 'role-1', 'approved assignment', 'org-1');
  });

  it('uses null scope for global grants and the exact stored scope for revocation', () => {
    const { api, component } = setup([link]);
    component.selectedTarget = 'role-1'; component.reason = 'global assignment';
    component.grant(new Event('submit'));
    expect(api.grant).toHaveBeenCalledWith('user_role', 'user-1', 'role-1', 'global assignment', undefined);
    spyOn(window, 'confirm').and.returnValue(true);
    component.reason = 'remove old scope'; component.revoke(link);
    expect(api.revoke).toHaveBeenCalledWith('user_role', 'user-1', 'role-1', 'remove old scope', 'org-1');
  });

  it('keeps a forbidden catalog failure visible and prevents grant', () => {
    const { api, component, fixture } = setup();
    const forbidden: ApiFailure = { kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'test', fields: [] };
    api.organizations.and.returnValue(throwError(() => forbidden));
    component.loadOrganizations(); component.scope = 'organization'; component.selectedTarget = 'role-1'; component.reason = 'valid reason';
    fixture.detectChanges();
    expect(component.organizationFailureKey()).toBe('adminUi.forbidden');
    expect(fixture.nativeElement.textContent).toContain('Você não tem permissão');
    component.grant(new Event('submit'));
    expect(api.grant).not.toHaveBeenCalled();
  });
});
