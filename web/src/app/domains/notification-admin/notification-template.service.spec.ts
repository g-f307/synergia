import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { NotificationTemplateService } from './notification-template.service';

describe('NotificationTemplateService', () => {
  let service: NotificationTemplateService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(NotificationTemplateService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('keeps filters and pagination in the catalog request', () => {
    service.list({ notification_type: 'execution.completed', channel: 'email', locale: 'en-US', state: 'active', sort: 'oldest', page: 2, page_size: 10 }).subscribe();
    const request = http.expectOne((candidate) => candidate.url === `${environment.apiUrl}/admin/notification-templates`);
    expect(request.request.params.get('notification_type')).toBe('execution.completed');
    expect(request.request.params.get('channel')).toBe('email');
    expect(request.request.params.get('locale')).toBe('en-US');
    expect(request.request.params.get('state')).toBe('active');
    expect(request.request.params.get('sort')).toBe('oldest');
    expect(request.request.params.get('page')).toBe('2');
    request.flush({ items: [], page: 2, page_size: 10, total: 0, pages: 0, sort: 'oldest' });
  });

  it('uses explicit lifecycle endpoints and optimistic versions', () => {
    service.publish('revision id', 3, 'homologado').subscribe();
    const publish = http.expectOne(`${environment.apiUrl}/admin/notification-templates/revision%20id/publish`);
    expect(publish.request.method).toBe('POST');
    expect(publish.request.body).toEqual({ row_version: 3, reason: 'homologado' });
    publish.flush({});

    service.deactivate('revision id', 4, 'substituído').subscribe();
    const deactivate = http.expectOne(`${environment.apiUrl}/admin/notification-templates/revision%20id/deactivate`);
    expect(deactivate.request.body).toEqual({ row_version: 4, reason: 'substituído' });
    deactivate.flush({});
  });
});
