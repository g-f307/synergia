import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AdminService } from './admin.service';
import { AdminUsersComponent } from './admin-users.component';

describe('AdminUsersComponent', () => {
  const user = {
    id: 'user-1', display_name: 'Marina Costa', status: 'active' as const,
    emails: [{ email: 'marina@example.invalid', is_primary: true, is_verified: true }],
    version: 3, created_at: '2026-10-10T10:00:00Z', updated_at: '2026-10-18T10:00:00Z',
    deactivated_at: null, last_login_at: null
  };

  function setup() {
    const api = {
      users: jasmine.createSpy().and.returnValue(of({ items: [user], page: 1, page_size: 25, total: 1, pages: 1, sort: 'created_at,id' })),
      changeUserStatus: jasmine.createSpy().and.returnValue(of({ ...user, status: 'inactive', version: 4 }))
    };
    TestBed.configureTestingModule({
      imports: [AdminUsersComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { queryParamMap: of(convertToParamMap({})), snapshot: { queryParamMap: convertToParamMap({}) } } },
        { provide: AdminService, useValue: api }
      ]
    });
    const fixture = TestBed.createComponent(AdminUsersComponent);
    fixture.detectChanges();
    return { api, fixture, component: fixture.componentInstance };
  }

  it('exposes create, read, update and auditable deactivation from the user catalog', () => {
    const { fixture } = setup();
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('a[href="/admin/users/new"]')).not.toBeNull();
    const edit = root.querySelector<HTMLAnchorElement>('a[href="/admin/users/user-1"]');
    expect(edit?.getAttribute('aria-label')).toContain('Editar');
    expect(edit?.querySelector('svg')).not.toBeNull();
    expect(edit?.textContent?.trim()).toBe('');
    expect(root.textContent).toContain('Marina Costa');
    expect(root.textContent).toContain('marina@example.invalid');
    const deactivate = root.querySelector<HTMLButtonElement>('[data-action="deactivate-user"]');
    expect(deactivate?.getAttribute('aria-label')).toContain('Desativar');
    expect(deactivate?.querySelector('svg')).not.toBeNull();
    expect(deactivate?.textContent?.trim()).toBe('');
    expect(root.querySelector('.admin-filter-actions button[type="submit"]')).not.toBeNull();
    expect(root.querySelector('.admin-filter-actions button[type="button"]')).not.toBeNull();
    expect(getComputedStyle(root.querySelector('.admin-page') as HTMLElement).overflowY).toBe('auto');
  });

  it('requires a reason before deactivating a user and refreshes the catalog after success', () => {
    const { api, fixture } = setup();
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-action="deactivate-user"]')?.click();
    fixture.detectChanges();
    const form = (fixture.nativeElement as HTMLElement).querySelector<HTMLFormElement>('.lifecycle-form')!;
    form.dispatchEvent(new Event('submit'));
    fixture.detectChanges();
    expect(api.changeUserStatus).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Informe um motivo');

    const textarea = form.querySelector<HTMLTextAreaElement>('textarea')!;
    textarea.value = 'Acesso encerrado para validação';
    textarea.dispatchEvent(new Event('input'));
    form.dispatchEvent(new Event('submit'));
    expect(api.changeUserStatus).toHaveBeenCalledWith('user-1', 'deactivate', 3, 'Acesso encerrado para validação');
    expect(api.users).toHaveBeenCalledTimes(2);
  });

  it('presents deactivation as a scoped destructive confirmation', () => {
    const { fixture } = setup();
    const root = fixture.nativeElement as HTMLElement;

    root.querySelector<HTMLButtonElement>('[data-action="deactivate-user"]')?.click();
    fixture.detectChanges();

    const dialog = root.querySelector<HTMLElement>('.admin-lifecycle-dialog')!;
    const subject = dialog.querySelector<HTMLElement>('.admin-modal-subject')!;
    const actions = dialog.querySelector<HTMLElement>('.admin-modal-actions')!;
    const buttons = actions.querySelectorAll<HTMLButtonElement>('button');

    expect(dialog.classList).toContain('is-destructive');
    expect(dialog.getAttribute('aria-describedby')).toBe('user-lifecycle-description');
    expect(subject.textContent).toContain('Usuário');
    expect(subject.textContent).toContain('Marina Costa');
    expect(buttons[0].textContent).toContain('Cancelar');
    expect(buttons[1].textContent).toContain('Desativar');
    expect(buttons[1].classList).toContain('danger');
  });
});
