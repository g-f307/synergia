import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { QueryService } from './query.service';

describe('QueryService', () => {
  let service: QueryService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(QueryService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('preserves textual identifiers and pagination in operational search', () => {
    service.search('serial', '000-A/7', 2, 10, 'identifier_asc').subscribe();
    const request = http.expectOne(candidate => candidate.url === `${environment.apiUrl}/search`);
    expect(request.request.params.get('type')).toBe('serial');
    expect(request.request.params.get('query')).toBe('000-A/7');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('page_size')).toBe('10');
    expect(request.request.params.get('sort')).toBe('identifier_asc');
    request.flush({ items: [], pagination: { page: 2, page_size: 10, total: 0, pages: 0 }, sort: 'identifier_asc', entity_type: 'serial', query: '000-A/7', source: 'synergia.operational', generated_at: '2026-09-04T12:00:00Z' });
  });

  it('loads the consolidated Workorder instead of any local source', () => {
    service.workorder('WO-001', 'exec-001').subscribe();
    const request = http.expectOne(candidate => candidate.url === `${environment.apiUrl}/workorders/WO-001/consolidated-result`);
    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('execution_id')).toBe('exec-001');
    request.flush({ workorder: {}, classifications: [], pending_items: [], provenance: [] });
  });
});
