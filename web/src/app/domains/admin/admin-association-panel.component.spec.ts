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

  it('uses null scope for global grants', () => {
    const { api, component } = setup([link]);
    component.selectedTarget = 'role-1'; component.reason = 'global assignment';
    component.grant(new Event('submit'));
    expect(api.grant).toHaveBeenCalledWith('user_role', 'user-1', 'role-1', 'global assignment', undefined);
  });

  it('collects the revocation reason in the shared confirmation dialog', () => {
    const { api, fixture } = setup([link]);
    const root = fixture.nativeElement as HTMLElement;
    const revokeButton = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((button) => button.textContent?.includes('Revogar'))!;

    revokeButton.click(); fixture.detectChanges();

    const dialog = root.querySelector<HTMLElement>('.admin-lifecycle-dialog')!;
    expect(dialog).not.toBeNull();
    expect(dialog.textContent).toContain('gestor');
    expect(api.revoke).not.toHaveBeenCalled();

    const reason = dialog.querySelector<HTMLTextAreaElement>('textarea[name="revokeReason"]')!;
    reason.value = 'remove old scope';
    reason.dispatchEvent(new Event('input'));
    dialog.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

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

  it('keeps each relationship editor collapsed until the administrator opens it', () => {
    const { fixture } = setup([link]);
    const disclosure = fixture.nativeElement.querySelector('details.admin-association-disclosure') as HTMLDetailsElement;

    expect(disclosure).not.toBeNull();
    expect(disclosure.open).toBeFalse();
    expect(disclosure.querySelector('summary')?.textContent).toContain('Papéis do usuário');

    disclosure.querySelector<HTMLElement>('summary')?.click();
    fixture.detectChanges();

    expect(disclosure.open).toBeTrue();
  });

  it('uses one list boundary per relationship editor without nested decorative dividers', () => {
    const { fixture } = setup([link]);
    const root = fixture.nativeElement as HTMLElement;
    const section = root.querySelector('.admin-links') as HTMLElement;
    const content = root.querySelector('.admin-association-content') as HTMLElement;
    const form = root.querySelector('.admin-association-form') as HTMLElement;

    expect(getComputedStyle(section).borderTopWidth).toBe('0px');
    expect(getComputedStyle(section).borderBottomWidth).toBe('1px');
    expect(getComputedStyle(content).borderTopWidth).toBe('0px');
    expect(getComputedStyle(form).borderTopWidth).toBe('0px');
  });
});
