import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, ParamMap, convertToParamMap, provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { NotificationTemplateEditorComponent } from './notification-template-editor.component';
import { NotificationTemplateService } from './notification-template.service';

const policy = {
  events: [{ notification_type: 'execution.completed', required_permission: 'execution.read', resource_type: 'execution', allowed_placeholders: ['execution_id'] }],
  channels: ['in_app', 'email'] as const,
  locales: ['pt-BR', 'en-US'] as const,
  external_delivery: 'local_capture' as const,
  external_delivery_corporate: false
};
const item = {
  id: '77777777-7777-4777-8777-777777777777', notification_type: 'execution.completed', channel: 'in_app' as const, locale: 'pt-BR' as const,
  version_number: 2, version_label: '2.0.0', state: 'active' as const, title_template: 'Concluída', body_template: 'Execução {execution_id}', allowed_placeholders: ['execution_id'], row_version: 2,
  created_by_user_id: null, created_reason: 'teste', created_at: '2026-09-22T12:00:00Z', updated_by_user_id: null, updated_reason: null, updated_at: '2026-09-22T12:00:00Z', published_by_user_id: null, published_reason: 'homologado', published_at: '2026-09-22T12:00:00Z', deactivated_by_user_id: null, deactivated_reason: null, deactivated_at: null
};

describe('NotificationTemplateEditorComponent', () => {
  let fixture: ComponentFixture<NotificationTemplateEditorComponent>;
  let preview: jasmine.Spy;
  let list: jasmine.Spy;
  let get: jasmine.Spy;
  let publish: jasmine.Spy;
  let deactivate: jasmine.Spy;
  let route: { snapshot: { paramMap: ParamMap } };

  beforeEach(async () => {
    preview = jasmine.createSpy().and.returnValue(of({ title: '<img src=x onerror=alert(1)>', body: '<script>alert(1)</script>', sample_data: { execution_id: 'EXEC-SYNTHETIC-001' }, synthetic: true }));
    list = jasmine.createSpy().and.returnValue(of({ items: [item], page: 1, page_size: 100, total: 1, pages: 1, sort: 'newest' }));
    get = jasmine.createSpy().and.returnValue(of(item));
    publish = jasmine.createSpy().and.returnValue(of({ ...item, state: 'active' }));
    deactivate = jasmine.createSpy().and.returnValue(of({ ...item, state: 'inactive' }));
    route = { snapshot: { paramMap: convertToParamMap({ templateId: item.id }) } };
    await TestBed.configureTestingModule({
      imports: [NotificationTemplateEditorComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: route },
        { provide: NotificationTemplateService, useValue: { policy: () => of(policy), get, list, preview, publish, deactivate } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(NotificationTemplateEditorComponent);
    fixture.detectChanges();
  });

  it('keeps published content readonly and exposes immutable history', () => {
    expect(fixture.nativeElement.querySelector('input[name="title"]').readOnly).toBeTrue();
    expect(fixture.nativeElement.querySelector('textarea[name="body"]').readOnly).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('Histórico de versões');
    expect(fixture.nativeElement.querySelector('button[type="submit"]')).toBeNull();
  });

  it('groups an existing version into overview, composer, controls, and history', () => {
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('.admin-detail-heading')).not.toBeNull();
    expect(root.querySelector('.template-overview')?.textContent).toContain('2.0.0');
    expect(root.querySelector('.template-overview')?.textContent).toContain('execution.completed');
    expect(root.querySelector('.template-composer .template-document')).not.toBeNull();
    expect(root.querySelector('.template-composer .template-context')).not.toBeNull();
    expect(root.querySelector('.template-change-footer .template-version-actions')).not.toBeNull();
    expect(root.querySelector('.template-history-list')).not.toBeNull();
  });

  it('orders draft creation from configuration to content, context, and final action', () => {
    fixture.destroy();
    route.snapshot.paramMap = convertToParamMap({});
    fixture = TestBed.createComponent(NotificationTemplateEditorComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('.admin-detail-heading')?.textContent).toContain('Criar rascunho de template');
    expect(root.querySelectorAll('.template-composer .template-settings select').length).toBe(3);
    expect(root.querySelector('.template-composer .template-document')).not.toBeNull();
    expect(root.querySelector('.template-composer .template-context')).not.toBeNull();
    expect(root.querySelector('.template-change-footer .admin-form-actions button[type="submit"]')?.textContent).toContain('Criar rascunho');
    expect(root.querySelector('.template-overview')).toBeNull();
    expect(root.querySelector('.template-history-list')).toBeNull();
  });

  it('aligns the change-control heading with the top of the reason field', () => {
    const reason = fixture.nativeElement.querySelector('.template-reason') as HTMLElement;

    expect(getComputedStyle(reason).alignItems).toBe('start');
  });

  it('renders synthetic preview as text instead of executable markup', () => {
    fixture.componentInstance.requestPreview(); fixture.detectChanges();
    const previewElement = fixture.nativeElement.querySelector('.template-preview');
    expect(previewElement.textContent).toContain('<script>alert(1)</script>');
    expect(previewElement.querySelector('script')).toBeNull();
    expect(previewElement.querySelector('img')).toBeNull();
  });

  it('confirms deactivation in the shared dialog before changing the active version', () => {
    const root = fixture.nativeElement as HTMLElement;
    const deactivateButton = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((button) => button.textContent?.includes('Desativar versão'))!;

    deactivateButton.click(); fixture.detectChanges();

    const dialog = root.querySelector<HTMLElement>('.admin-lifecycle-dialog')!;
    expect(dialog).not.toBeNull();
    expect(dialog.textContent).toContain('2.0.0');
    expect(deactivate).not.toHaveBeenCalled();

    const reason = dialog.querySelector<HTMLTextAreaElement>('textarea[name="transitionReason"]')!;
    reason.value = 'retirada aprovada';
    reason.dispatchEvent(new Event('input'));
    dialog.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(root.textContent).toContain('Publicada e inativa');
  });

  it('confirms publication in the shared dialog before activating a draft', () => {
    fixture.destroy();
    const draft = { ...item, state: 'draft' as const };
    get.and.returnValue(of(draft));
    publish.and.returnValue(of({ ...draft, state: 'active' as const }));
    fixture = TestBed.createComponent(NotificationTemplateEditorComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const publishButton = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((button) => button.textContent?.includes('Publicar versão'))!;

    publishButton.click(); fixture.detectChanges();

    const dialog = root.querySelector<HTMLElement>('.admin-lifecycle-dialog')!;
    expect(dialog).not.toBeNull();
    expect(publish).not.toHaveBeenCalled();

    const reason = dialog.querySelector<HTMLTextAreaElement>('textarea[name="transitionReason"]')!;
    reason.value = 'publicação aprovada';
    reason.dispatchEvent(new Event('input'));
    dialog.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit'));
    fixture.detectChanges();

    expect(root.textContent).toContain('Publicada e ativa');
  });

  it('does not hide a history failure as an empty history', () => {
    fixture.destroy();
    list.and.returnValue(throwError(() => ({
      kind: 'unavailable', status: 503, code: 'database_unavailable', message: 'safe',
      correlationId: 'history-failure', fields: []
    } as ApiFailure)));
    fixture = TestBed.createComponent(NotificationTemplateEditorComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('temporariamente indisponível');
  });

  it('makes revisions after the first 100 accessible through history pagination', () => {
    fixture.destroy();
    const oldest = { ...item, id: '88888888-8888-4888-8888-888888888888', version_number: 1 };
    list.and.returnValues(
      of({ items: [item], page: 1, page_size: 100, total: 101, pages: 2, sort: 'newest' }),
      of({ items: [oldest], page: 2, page_size: 100, total: 101, pages: 2, sort: 'newest' })
    );
    fixture = TestBed.createComponent(NotificationTemplateEditorComponent);
    fixture.detectChanges();

    const next: HTMLButtonElement = fixture.nativeElement.querySelector('.history-pagination button:last-child');
    next.click(); fixture.detectChanges();

    expect(list.calls.mostRecent().args[0].page).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('2 / 2');
    expect(fixture.nativeElement.textContent).toContain('v1');
  });
});
