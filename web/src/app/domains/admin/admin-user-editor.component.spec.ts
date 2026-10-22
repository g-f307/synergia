import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { AdminUser } from './admin.models';
import { AdminService } from './admin.service';
import { AdminUserEditorComponent } from './admin-user-editor.component';

describe('AdminUserEditorComponent', () => {
  const id = '11111111-1111-4111-8111-111111111111';
  const user = (version = 4): AdminUser => ({
    id, display_name: 'Test Admin', status: 'active',
    emails: [{ email: 'admin@example.invalid', is_primary: true, is_verified: true }],
    version, created_at: '', updated_at: '', deactivated_at: null, last_login_at: null
  });
  const emptyPage = { items: [], page: 1, page_size: 25, total: 0, pages: 0, sort: 'granted_at,kind,id' };
  const conflict: ApiFailure = { kind: 'conflict', status: 409, code: 'user_version_conflict', message: 'safe', correlationId: 'test-correlation', fields: [] };

  function setup(edit: boolean) {
    const api = {
      user: jasmine.createSpy().and.returnValue(of(user())),
      createUser: jasmine.createSpy().and.returnValue(of(user())),
      updateUser: jasmine.createSpy().and.returnValue(of(user(5))),
      changeUserStatus: jasmine.createSpy().and.returnValue(of(user(5))),
      effectivePermissions: jasmine.createSpy().and.returnValue(of({ user_id: id, permissions: [] })),
      associations: jasmine.createSpy().and.returnValue(of(emptyPage)),
      groups: jasmine.createSpy().and.returnValue(of(emptyPage)),
      roles: jasmine.createSpy().and.returnValue(of(emptyPage)),
      permissions: jasmine.createSpy().and.returnValue(of([])),
      organizations: jasmine.createSpy().and.returnValue(of(emptyPage))
    };
    TestBed.configureTestingModule({
      imports: [AdminUserEditorComponent],
      providers: [provideRouter([]), { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap(edit ? { userId: id } : {}) } } }, { provide: AdminService, useValue: api }]
    });
    const router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
    const fixture = TestBed.createComponent(AdminUserEditorComponent);
    fixture.detectChanges();
    return { api, fixture, component: fixture.componentInstance };
  }

  it('creates a user with multiple emails and a justification', () => {
    const { api, component } = setup(false);
    component.displayName = 'New person'; component.reason = 'onboarding approved';
    component.emails = [
      { email: 'one@example.invalid', is_primary: true, is_verified: false },
      { email: 'two@example.invalid', is_primary: false, is_verified: false }
    ];
    component.save(new Event('submit'));
    expect(api.createUser).toHaveBeenCalledWith(jasmine.objectContaining({ display_name: 'New person', emails: component.emails, reason: 'onboarding approved' }));
  });

  it('presents user creation as data followed by a traceable final action', () => {
    const { fixture } = setup(false);
    const root = fixture.nativeElement as HTMLElement;
    const form = root.querySelector('.admin-create-form');
    const changeControl = form?.querySelector('.admin-change-section');

    expect(form).not.toBeNull();
    expect(changeControl?.querySelector('h2')?.textContent).toContain('Controle da alteração');
    expect(changeControl?.querySelector('textarea[name="reason"]')).not.toBeNull();
    expect(changeControl?.querySelector('button[type="submit"]')).toBeNull();
    expect(form?.querySelector(':scope > .admin-editor-actions button[type="submit"]')?.textContent).toContain('Salvar');
    expect(getComputedStyle(changeControl as HTMLElement).alignItems).toBe('start');
  });

  it('uses compact design-system choices for primary and verified email states', () => {
    const { fixture } = setup(false);
    const root = fixture.nativeElement as HTMLElement;
    const choices = root.querySelectorAll<HTMLElement>('.admin-email-choice');

    expect(choices.length).toBe(2);
    expect(choices[0].querySelector('input[type="radio"]')).not.toBeNull();
    expect(choices[1].querySelector('input[type="checkbox"]')).not.toBeNull();
    expect(getComputedStyle(choices[0]).backgroundColor).toBe('rgba(0, 0, 0, 0)');
    expect(parseFloat(getComputedStyle(choices[0].querySelector<HTMLInputElement>('input')!).width)).toBeLessThanOrEqual(18);
  });

  it('preserves current data after a 409 and reloads the server version', () => {
    const { api, component, fixture } = setup(true);
    api.updateUser.and.returnValue(throwError(() => conflict));
    component.reason = 'correct display name'; component.displayName = 'Edited';
    component.save(new Event('submit'));
    expect(api.updateUser).toHaveBeenCalledWith(id, jasmine.objectContaining({ version: 4 }));
    expect(component.failure()?.kind).toBe('conflict');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Recarregue antes de tentar novamente');
    api.user.and.returnValue(of(user(5)));
    component.reload();
    expect(component.user()?.version).toBe(5);
  });

  it('shows the last-administrator denial without claiming success', () => {
    const { api, component } = setup(true);
    const deny: ApiFailure = { ...conflict, code: 'last_active_admin' };
    api.changeUserStatus.and.returnValue(throwError(() => deny));
    component.reason = 'rotation approved'; component.changeStatus('deactivate');
    expect(api.changeUserStatus).toHaveBeenCalledWith(id, 'deactivate', 4, 'rotation approved');
    expect(component.failureKey()).toBe('adminUi.lastAdmin');
    expect(component.user()?.status).toBe('active');
  });

  it('uses the shared confirmation dialog for destructive detail actions', () => {
    const { api, fixture } = setup(true);
    const root = fixture.nativeElement as HTMLElement;

    root.querySelector<HTMLButtonElement>('[data-action="deactivate-user-detail"]')?.click();
    fixture.detectChanges();

    const dialog = root.querySelector<HTMLElement>('.admin-lifecycle-dialog')!;
    expect(dialog).not.toBeNull();
    expect(dialog.classList).toContain('is-destructive');
    expect(dialog.textContent).toContain('Test Admin');
    expect(api.changeUserStatus).not.toHaveBeenCalled();

    const textarea = dialog.querySelector<HTMLTextAreaElement>('textarea')!;
    textarea.value = 'Encerramento aprovado';
    textarea.dispatchEvent(new Event('input'));
    dialog.querySelector<HTMLFormElement>('form')?.dispatchEvent(new Event('submit'));

    expect(api.changeUserStatus).toHaveBeenCalledWith(id, 'deactivate', 4, 'Encerramento aprovado');
  });

  it('organizes editing and lifecycle controls in the shared administrative hierarchy', () => {
    const { fixture } = setup(true);
    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('.admin-detail-heading a[aria-label]')).not.toBeNull();
    expect(root.querySelector('h1')?.textContent).toContain('Detalhes do usuário');
    expect(root.querySelector('.admin-record-form h2')?.textContent).toContain('Dados do usuário');
    expect(root.querySelector('.admin-lifecycle h2')?.textContent).toContain('Controle de acesso');
    expect(root.querySelector('.admin-edit-form')).not.toBeNull();
    expect(root.querySelector('.admin-association-stack')).toBeNull();
    expect(getComputedStyle(root.querySelector('.admin-page') as HTMLElement).overflowY).toBe('auto');
  });

  it('reveals access relationships only when the administrator selects that section', () => {
    const { fixture } = setup(true);
    const root = fixture.nativeElement as HTMLElement;
    const tabs = root.querySelector('[role="tablist"]');
    const accessTab = root.querySelector<HTMLButtonElement>('button[data-section="associations"]');

    expect(tabs).not.toBeNull();
    expect(accessTab?.getAttribute('aria-selected')).toBe('false');
    const detailsTab = root.querySelector<HTMLButtonElement>('button[data-section="details"]')!;
    expect(getComputedStyle(detailsTab).backgroundColor).toBe('rgba(0, 0, 0, 0)');
    expect(detailsTab.textContent).toContain('Dados e estado');
    expect(root.querySelector('.admin-record-form')).not.toBeNull();
    expect(root.querySelector('.admin-association-stack')).toBeNull();

    accessTab?.click();
    fixture.detectChanges();

    expect(accessTab?.getAttribute('aria-selected')).toBe('true');
    expect(root.querySelector('.admin-record-form')).toBeNull();
    expect(root.querySelector('.admin-association-stack')).not.toBeNull();
  });

  it('reserves divider lines for the page boundary instead of every editor section', () => {
    const { fixture } = setup(true);
    const root = fixture.nativeElement as HTMLElement;

    expect(getComputedStyle(root.querySelector('.admin-detail-heading') as HTMLElement).borderBottomWidth).toBe('1px');
    expect(getComputedStyle(root.querySelector('.admin-editor-tabs') as HTMLElement).borderBottomWidth).toBe('0px');
    expect(getComputedStyle(root.querySelector('.admin-record-form') as HTMLElement).borderTopWidth).toBe('0px');
    expect(getComputedStyle(root.querySelector('.admin-change-section') as HTMLElement).borderTopWidth).toBe('0px');
    expect(getComputedStyle(root.querySelector('.admin-lifecycle') as HTMLElement).borderTopWidth).toBe('0px');
  });
});
