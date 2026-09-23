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

  it('shows the catalog and makes the absence of corporate delivery explicit', () => {
    expect(fixture.nativeElement.textContent).toContain('Nenhuma versão encontrada');
    expect(fixture.nativeElement.textContent).toContain('desabilitada');
    expect(fixture.nativeElement.textContent).toContain('SMTP corporativo');
  });

  it('distinguishes forbidden access from temporary unavailability', () => {
    fixture.destroy();
    apiPolicy.and.returnValue(throwError(() => ({ kind: 'forbidden', status: 403, code: 'access_denied', message: 'safe', correlationId: 'forbidden-test', fields: [] } as ApiFailure)));
    fixture = TestBed.createComponent(NotificationTemplateListComponent);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('não possui permissão administrativa');
    expect(fixture.nativeElement.textContent).not.toContain('temporariamente indisponível');
  });
});
