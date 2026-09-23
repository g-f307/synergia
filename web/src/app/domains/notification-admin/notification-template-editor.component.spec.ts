import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
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

  beforeEach(async () => {
    preview = jasmine.createSpy().and.returnValue(of({ title: '<img src=x onerror=alert(1)>', body: '<script>alert(1)</script>', sample_data: { execution_id: 'EXEC-SYNTHETIC-001' }, synthetic: true }));
    list = jasmine.createSpy().and.returnValue(of({ items: [item], page: 1, page_size: 100, total: 1, pages: 1, sort: 'newest' }));
    await TestBed.configureTestingModule({
      imports: [NotificationTemplateEditorComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ templateId: item.id }) } } },
        { provide: NotificationTemplateService, useValue: { policy: () => of(policy), get: () => of(item), list, preview } }
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

  it('renders synthetic preview as text instead of executable markup', () => {
    fixture.componentInstance.requestPreview(); fixture.detectChanges();
    const previewElement = fixture.nativeElement.querySelector('.template-preview');
    expect(previewElement.textContent).toContain('<script>alert(1)</script>');
    expect(previewElement.querySelector('script')).toBeNull();
    expect(previewElement.querySelector('img')).toBeNull();
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
