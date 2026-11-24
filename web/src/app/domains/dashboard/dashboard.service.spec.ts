import { completeQuantityCoverage } from '../../../testing/indicator-fixtures';
import { Indicators } from '../../shared/api/operational.models';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { DashboardService } from './dashboard.service';
import { executionAggregate } from '../../../testing/execution-fixtures';

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
    const response: Indicators = { generated_at: '2026-09-03T12:00:00Z', source: 'synergia.operational', organizations: [], filters: { organization_id: null, date_from: null, date_to: null }, executions: { completed: 2 }, execution_summary: executionAggregate({ completed: 2 }), workorders: { total: 3, partially_released: 1 }, workorders_current: { total: 3, partially_released: 1 }, quantities_coverage: completeQuantityCoverage({planned:10,produced:8,received:7,released:6}), pending_items: { open: 1 }, quantities: { planned: 10, produced: 8, received: 7, released: 6 } };
    service.getIndicators({ organizationId: 'org-1', dateFrom: '2026-08-01', dateTo: '2026-08-31' }).subscribe((value) => expect(value).toEqual(response));

    const request = http.expectOne((candidate) => candidate.url === `${environment.apiUrl}/indicators`);
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('organization_id')).toBe('org-1');
    expect(request.request.params.get('started_from')).toBe('2026-08-01T04:00:00Z');
    expect(request.request.params.get('started_to')).toBe('2026-09-01T03:59:59.999999Z');
    request.flush(response);
  });

  it('loads related records with the same filter context', () => {
    service.getRelated('pending-items', { organizationId: 'org-1', dateFrom: '2026-08-01', dateTo: '2026-08-31' }).subscribe();
    const request = http.expectOne((candidate) => candidate.url.endsWith('/indicators/pending-items'));
    expect(request.request.params.get('organization_id')).toBe('org-1');
    expect(request.request.params.get('started_from')).toBe('2026-08-01T04:00:00Z');
    request.flush({ items: [], pagination: { page: 1, pages: 0, total: 0 }, entity: 'pending-items' });
  });
  it('explicitly requests current Workorders and allows an explicitly historical list', () => {
    for (const view of [undefined,'history'] as const) {
      service.getRelated('workorders', { page:2, view }).subscribe();
      const request = http.expectOne(candidate => candidate.url.endsWith('/indicators/workorders'));
      expect(request.request.params.get('view')).toBe(view ?? 'current');
      expect(request.request.params.get('page')).toBe('2');
      request.flush({ items:[],pagination:{page:2,pages:0,total:0},entity:'workorders',view:view ?? 'current',scope:{permissions:['dashboard.read','business.read'],organization_ids:[]} });
    }
  });

  it('does not send Workorder selection to the execution or pending lists', () => {
    for (const entity of ['executions','pending-items'] as const) {
      service.getRelated(entity, {view:'current'}).subscribe();
      const request = http.expectOne(candidate => candidate.url.endsWith(`/indicators/${entity}`));
      expect(request.request.params.has('view')).toBeFalse();
      request.flush({items:[]});
    }
  });

});
