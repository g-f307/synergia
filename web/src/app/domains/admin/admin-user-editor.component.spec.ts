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
    spyOn(window, 'confirm').and.returnValue(true);
    component.reason = 'rotation approved'; component.changeStatus('deactivate');
    expect(api.changeUserStatus).toHaveBeenCalledWith(id, 'deactivate', 4, 'rotation approved');
    expect(component.failureKey()).toBe('adminUi.lastAdmin');
    expect(component.user()?.status).toBe('active');
  });
});
