import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AdminAccessEditorComponent } from './admin-access-editor.component';
import { AdminService } from './admin.service';

describe('AdminAccessEditorComponent', () => {
  function setup(kind: 'groups' | 'roles', id?: string) {
    const group = { id: 'group-1', group_name: 'Qualidade OQC', external_reference: 'OQC', is_active: true, version: 2, created_at: '', updated_at: '', deactivated_at: null };
    const role = { id: 'role-1', role_key: 'quality.analyst', description: 'Analisa qualidade', is_active: true, version: 2, created_at: '', updated_at: '', deactivated_at: null };
    const emptyPage = { items: [], page: 1, page_size: 25, total: 0, pages: 0, sort: 'name,id' };
    const api = {
      group: jasmine.createSpy().and.returnValue(of(group)),
      role: jasmine.createSpy().and.returnValue(of(role)),
      associations: jasmine.createSpy().and.returnValue(of(emptyPage)),
      users: jasmine.createSpy().and.returnValue(of(emptyPage)),
      groups: jasmine.createSpy().and.returnValue(of(emptyPage)),
      roles: jasmine.createSpy().and.returnValue(of(emptyPage)),
      permissions: jasmine.createSpy().and.returnValue(of([])),
      organizations: jasmine.createSpy().and.returnValue(of(emptyPage)),
      createGroup: jasmine.createSpy().and.returnValue(of(group)),
      createRole: jasmine.createSpy().and.returnValue(of(role)),
      updateGroup: jasmine.createSpy().and.returnValue(of(group)),
      updateRole: jasmine.createSpy().and.returnValue(of(role)),
      changeGroupStatus: jasmine.createSpy().and.returnValue(of({ ...group, is_active: false, version: 3 })),
      changeRoleStatus: jasmine.createSpy().and.returnValue(of({ ...role, is_active: false, version: 3 }))
    };
    TestBed.configureTestingModule({
      imports: [AdminAccessEditorComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { data: { kind }, paramMap: convertToParamMap(id ? { [kind === 'groups' ? 'groupId' : 'roleId']: id } : {}) } } },
        { provide: AdminService, useValue: api }
      ]
    });
    const fixture = TestBed.createComponent(AdminAccessEditorComponent);
    fixture.detectChanges();
    return { fixture, api };
  }

  it('uses the same detail hierarchy for groups and exposes update and lifecycle actions', () => {
    const { fixture } = setup('groups', 'group-1');
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('.admin-detail-heading a[aria-label]')).not.toBeNull();
    expect(root.querySelector('.admin-record-form h2')?.textContent).toContain('Dados do grupo');
    expect(root.querySelector('.admin-lifecycle h2')?.textContent).toContain('Ciclo de vida');
    expect(root.querySelector<HTMLButtonElement>('.admin-lifecycle button')?.textContent).toContain('Desativar');
    expect(root.querySelector('.admin-edit-form')).not.toBeNull();
    expect(root.querySelector('.admin-association-stack')).toBeNull();
  });

  it('uses the shared confirmation dialog before deactivating a group from its details', () => {
    const { fixture, api } = setup('groups', 'group-1');
    const root = fixture.nativeElement as HTMLElement;

    root.querySelector<HTMLButtonElement>('[data-action="deactivate-access-detail"]')?.click();
    fixture.detectChanges();

    const dialog = root.querySelector<HTMLElement>('.admin-lifecycle-dialog')!;
    expect(dialog).not.toBeNull();
    expect(dialog.classList).toContain('is-destructive');
    expect(dialog.textContent).toContain('Qualidade OQC');
    expect(api.changeGroupStatus).not.toHaveBeenCalled();

    const textarea = dialog.querySelector<HTMLTextAreaElement>('textarea')!;
    textarea.value = 'Grupo substituído';
    textarea.dispatchEvent(new Event('input'));
    dialog.querySelector<HTMLFormElement>('form')?.dispatchEvent(new Event('submit'));

    expect(api.changeGroupStatus).toHaveBeenCalledWith('group-1', 'deactivate', 2, 'Grupo substituído');
  });

  for (const kind of ['groups', 'roles'] as const) {
    it(`separates ${kind} record editing from its access relationships`, () => {
      const { fixture } = setup(kind, `${kind}-1`);
      const root = fixture.nativeElement as HTMLElement;
      const accessTab = root.querySelector<HTMLButtonElement>('button[data-section="associations"]');

      expect(root.querySelector('[role="tablist"]')).not.toBeNull();
      expect(root.querySelector('.admin-record-form')).not.toBeNull();
      expect(root.querySelector('.admin-association-stack')).toBeNull();

      accessTab?.click();
      fixture.detectChanges();

      expect(accessTab?.getAttribute('aria-selected')).toBe('true');
      expect(root.querySelector('.admin-record-form')).toBeNull();
      expect(root.querySelector('.admin-association-stack')).not.toBeNull();
    });
  }

  it('keeps detail fields aligned and the save action separated from change-control input', () => {
    const { fixture } = setup('roles', 'role-1');
    const root = fixture.nativeElement as HTMLElement;
    const name = root.querySelector<HTMLInputElement>('input[name="name"]');
    const detail = root.querySelector<HTMLTextAreaElement>('textarea[name="detail"]');
    const changeControl = root.querySelector('.admin-change-section');

    expect(getComputedStyle(name as HTMLElement).height).toBe(getComputedStyle(detail as HTMLElement).height);
    expect(changeControl?.querySelector('button[type="submit"]')).toBeNull();
    expect(root.querySelector('.admin-editor-actions button[type="submit"]')).not.toBeNull();
  });

  for (const [kind, title] of [['groups', 'Novo grupo'], ['roles', 'Novo papel']] as const) {
    it(`presents ${kind} creation with the shared change-control hierarchy`, () => {
      const { fixture } = setup(kind);
      const root = fixture.nativeElement as HTMLElement;
      const form = root.querySelector('.admin-create-form');
      const changeControl = form?.querySelector('.admin-change-section');

      expect(root.querySelector('h1')?.textContent).toContain(title);
      expect(form).not.toBeNull();
      expect(changeControl?.querySelector('h2')?.textContent).toContain('Controle da alteração');
      expect(changeControl?.querySelector('textarea[name="reason"]')).not.toBeNull();
      expect(changeControl?.querySelector('button[type="submit"]')).toBeNull();
      expect(form?.querySelector(':scope > .admin-editor-actions button[type="submit"]')?.textContent).toContain('Salvar');
      expect(getComputedStyle(changeControl as HTMLElement).alignItems).toBe('start');
    });
  }

  it('keeps group creation fields at the same visual height', () => {
    const { fixture } = setup('groups');
    const root = fixture.nativeElement as HTMLElement;
    const name = root.querySelector<HTMLInputElement>('input[name="name"]');
    const detail = root.querySelector<HTMLTextAreaElement>('textarea[name="detail"]');

    expect(name).not.toBeNull();
    expect(detail).not.toBeNull();
    expect(getComputedStyle(name as HTMLElement).height).toBe(getComputedStyle(detail as HTMLElement).height);
  });
});
