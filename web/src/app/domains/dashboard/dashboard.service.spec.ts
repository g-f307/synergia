import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { DashboardService } from './dashboard.service';

describe('DashboardService', () => {
  let service: DashboardService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(DashboardService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('loads the protected indicators contract without inventing unsupported filters', () => {
    const response = { generated_at: '2026-09-03T12:00:00Z', source: 'synergia.operational', organizations: [], filters: { organization_id: null, date_from: null, date_to: null }, executions: { completed: 2 }, workorders: { total: 3, partially_released: 1 }, pending_items: { open: 1 }, quantities: { planned: 10, produced: 8, received: 7, released: 6 } };
    service.getIndicators({ organizationId: 'org-1', dateFrom: '2026-08-01', dateTo: '2026-08-31' }).subscribe((value) => expect(value).toEqual(response));

    const request = http.expectOne((candidate) => candidate.url === `${environment.apiUrl}/indicators`);
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('organization_id')).toBe('org-1');
    expect(request.request.params.get('date_from')).toBe('2026-08-01');
    expect(request.request.params.get('date_to')).toBe('2026-08-31');
    request.flush(response);
  });
});
