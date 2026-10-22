import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, UrlTree, convertToParamMap, provideRouter } from '@angular/router';
import { Subject, of, throwError } from 'rxjs';

import { ApiFailure } from '../../shared/api/api-error';
import { NotificationTemplateListComponent } from './notification-template-list.component';
import { NotificationTemplateService } from './notification-template.service';

const policy = {
  events: [{ notification_type: 'execution.completed', required_permission: 'execution.read', resource_type: 'execution', allowed_placeholders: ['execution_id'] }],
  channels: ['in_app', 'email'] as const,
  locales: ['pt-BR', 'en-US'] as const,
  external_delivery: 'disabled' as const,
  external_delivery_corporate: false
};

describe('NotificationTemplateListComponent', () => {
  let fixture: ComponentFixture<NotificationTemplateListComponent>;
  let apiPolicy: jasmine.Spy;
  let list: jasmine.Spy;
  let router: jasmine.SpyObj<Router>;

  beforeEach(async () => {
    apiPolicy = jasmine.createSpy().and.returnValue(of(policy));
    list = jasmine.createSpy().and.returnValue(of({ items: [], page: 1, page_size: 25, total: 0, pages: 0, sort: 'newest' }));
    router = jasmine.createSpyObj<Router>('Router', ['navigate', 'createUrlTree', 'serializeUrl'], { events: new Subject(), url: '/admin/notification-templates' });
    router.navigate.and.resolveTo(true); router.createUrlTree.and.returnValue({} as UrlTree); router.serializeUrl.and.returnValue('/');
    await TestBed.configureTestingModule({
      imports: [NotificationTemplateListComponent],
      providers: [
        provideRouter([]),
        { provide: Router, useValue: router },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParamMap: convertToParamMap({}) } } },
        { provide: NotificationTemplateService, useValue: { policy: apiPolicy, list } }
      ]
    }).compileComponents();
    fixture = TestBed.createComponent(NotificationTemplateListComponent);
    fixture.detectChanges();
  });

  it('keeps the delivery limitation out of the template catalog', () => {
    expect(fixture.nativeElement.textContent).toContain('Nenhuma versão encontrada');
    expect(fixture.nativeElement.querySelector('.template-policy-note')).toBeNull();
  });

  it('distinguishes forbidden access from temporary unavailability', () => {
    fixture.destroy();
    apiPolicy.and.returnValue(throwError(() => ({ kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'forbidden-test', fields: [] } as ApiFailure)));
    fixture = TestBed.createComponent(NotificationTemplateListComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('não possui permissão administrativa');
    expect(fixture.nativeElement.textContent).not.toContain('temporariamente indisponível');
  });

  it('uses the standardized catalog hierarchy and accessible icon actions', () => {
    fixture.destroy();
    list.and.returnValue(of({
      items: [{
        id: 'template-1', notification_type: 'execution.completed', channel: 'email', locale: 'pt-BR',
        version_number: 2, version_label: 'v2', state: 'active', title_template: 'Execução concluída',
        body_template: 'A execução foi concluída.', allowed_placeholders: ['execution_id'], row_version: 2,
        created_by_user_id: null, created_reason: 'Cadastro sintético', created_at: '2026-10-18T10:00:00Z',
        updated_by_user_id: null, updated_reason: null, updated_at: '2026-10-19T10:00:00Z',
        published_by_user_id: null, published_reason: null, published_at: null,
        deactivated_by_user_id: null, deactivated_reason: null, deactivated_at: null
      }],
      page: 1, page_size: 25, total: 1, pages: 1, sort: 'newest'
    }));
    fixture = TestBed.createComponent(NotificationTemplateListComponent);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('.admin-catalog-heading')).not.toBeNull();
    expect(root.querySelector('.admin-filter-panel')).not.toBeNull();
    expect(root.querySelector('.admin-results-heading')?.textContent).toContain('1 registro');
    const edit = root.querySelector<HTMLAnchorElement>('a.admin-icon-action');
    expect(edit?.getAttribute('aria-label')).toContain('Editar');
    expect(edit?.querySelector('svg')).not.toBeNull();
    expect(root.textContent).toContain('Execução concluída');
    expect(root.textContent).toContain('Publicada e ativa');
  });
});
