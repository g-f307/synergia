import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AdminAccessListComponent } from './admin-access-list.component';
import { AdminService } from './admin.service';

describe('AdminAccessListComponent', () => {
  function setup(kind: 'groups' | 'roles') {
    const item = kind === 'groups'
      ? { id: 'group-1', group_name: 'Qualidade OQC', external_reference: 'OQC', is_active: true, version: 2, created_at: '', updated_at: '2026-10-18T10:00:00Z', deactivated_at: null }
      : { id: 'role-1', role_key: 'quality_reviewer', description: 'Revisa classificações OQC.', is_active: true, version: 2, created_at: '', updated_at: '2026-10-18T10:00:00Z', deactivated_at: null };
    const page = { items: [item], page: 1, page_size: 25, total: 1, pages: 1, sort: 'name,id' };
    const api = {
      groups: jasmine.createSpy().and.returnValue(of(page)),
      roles: jasmine.createSpy().and.returnValue(of(page)),
      changeGroupStatus: jasmine.createSpy().and.returnValue(of({ ...item, is_active: false, version: 3 })),
      changeRoleStatus: jasmine.createSpy().and.returnValue(of({ ...item, is_active: false, version: 3 }))
    };
    TestBed.configureTestingModule({
      imports: [AdminAccessListComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { data: { kind } }, queryParamMap: of(convertToParamMap({})) } },
        { provide: AdminService, useValue: api }
      ]
    });
    const fixture = TestBed.createComponent(AdminAccessListComponent);
    fixture.detectChanges();
    return { api, fixture };
  }

  for (const kind of ['groups', 'roles'] as const) {
    it(`exposes the complete managed lifecycle in the ${kind} catalog`, () => {
      const { api, fixture } = setup(kind);
      const root = fixture.nativeElement as HTMLElement;
      expect(root.querySelector(`a[href="/admin/${kind}/new"]`)).not.toBeNull();
      const edit = root.querySelector<HTMLAnchorElement>(`a[href="/admin/${kind}/${kind === 'groups' ? 'group-1' : 'role-1'}"]`);
      expect(edit?.getAttribute('aria-label')).toContain('Editar');
      expect(edit?.querySelector('svg')).not.toBeNull();
      expect(edit?.textContent?.trim()).toBe('');
      const deactivate = root.querySelector<HTMLButtonElement>('[data-action="deactivate-access"]');
      expect(deactivate?.getAttribute('aria-label')).toContain('Desativar');
      expect(deactivate?.querySelector('svg')).not.toBeNull();
      expect(deactivate?.textContent?.trim()).toBe('');

      root.querySelector<HTMLButtonElement>('[data-action="deactivate-access"]')?.click();
      fixture.detectChanges();
      const dialog = root.querySelector<HTMLElement>('.admin-lifecycle-dialog')!;
      const subject = dialog.querySelector<HTMLElement>('.admin-modal-subject')!;
      const submit = dialog.querySelector<HTMLButtonElement>('button[type="submit"]')!;

      expect(dialog.classList).toContain('is-destructive');
      expect(dialog.getAttribute('aria-describedby')).toBe('access-lifecycle-description');
      expect(dialog.querySelector('h2')?.textContent).toContain(kind === 'groups' ? 'Desativar grupo' : 'Desativar papel');
      expect(subject.textContent).toContain(kind === 'groups' ? 'Grupo' : 'Papel');
      expect(subject.textContent).toContain(kind === 'groups' ? 'Qualidade OQC' : 'quality_reviewer');
      expect(submit.classList).toContain('danger');
      const textarea = root.querySelector<HTMLTextAreaElement>('.lifecycle-form textarea')!;
      textarea.value = 'Cadastro substituído para validação';
      textarea.dispatchEvent(new Event('input'));
      root.querySelector<HTMLFormElement>('.lifecycle-form')!.dispatchEvent(new Event('submit'));

      const service = kind === 'groups' ? api.changeGroupStatus : api.changeRoleStatus;
      expect(service).toHaveBeenCalledWith(kind === 'groups' ? 'group-1' : 'role-1', 'deactivate', 2, 'Cadastro substituído para validação');
    });
  }

  it('keeps the cancel action legible in a dark destructive dialog', () => {
    document.documentElement.setAttribute('data-theme', 'dark');
    try {
      const { fixture } = setup('groups');
      const root = fixture.nativeElement as HTMLElement;
      root.querySelector<HTMLButtonElement>('[data-action="deactivate-access"]')?.click();
      fixture.detectChanges();

      const cancel = root.querySelector<HTMLButtonElement>('.admin-modal-actions button.secondary')!;
      expect(getComputedStyle(cancel).backgroundColor).toBe('rgb(26, 26, 26)');
      expect(getComputedStyle(cancel).color).toBe('rgb(243, 244, 246)');
    } finally {
      document.documentElement.removeAttribute('data-theme');
    }
  });
});
