import { HttpEventType, provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ImportService } from './import.service';

describe('ImportService', () => {
  let service: ImportService;
  let http: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ImportService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('uploads a source as multipart and reports transfer progress', () => {
    const updates: unknown[] = [];
    service.upload('N-FP', new File(['workorder\nWO-1'], 'plan.csv', { type: 'text/csv' }), 'org-1').subscribe((value) => updates.push(value));
    const request = http.expectOne('http://localhost:8000/imports');
    expect(request.request.method).toBe('POST');
    expect(request.request.reportProgress).toBeTrue();
    expect(request.request.body.get('source')).toBe('N-FP');
    expect(request.request.body.get('organization_id')).toBe('org-1');
    request.event({ type: HttpEventType.UploadProgress, loaded: 5, total: 10 });
    request.flush({ execution_id: 'exec-1', status: 'completed', source: 'N-FP' });
    expect(updates).toEqual([
      { kind: 'progress', progress: 50 },
      jasmine.objectContaining({ kind: 'complete', result: jasmine.objectContaining({ execution_id: 'exec-1' }) })
    ]);
  });

  it('loads the active upload policy from the backend contract', () => {
    let maxBytes = 0;
    let organizationName = '';
    service.policy().subscribe((configuration) => {
      maxBytes = configuration.policies[0].max_bytes;
      organizationName = configuration.organizations[0].display_name;
    });
    const request = http.expectOne('http://localhost:8000/imports/policy');
    expect(request.request.method).toBe('GET');
    request.flush({
      policies: [{ source: 'N-FP', allowed_extensions: ['csv'], max_bytes: 4096 }],
      organizations: [{ id: 'org-1', organization_code: 'ORG-1', display_name: 'Organization 1' }]
    });
    expect(maxBytes).toBe(4096);
    expect(organizationName).toBe('Organization 1');
  });

  it('reads persisted summary and retains response correlation for support', () => {
    let correlation: string | null | undefined;
    service.resultSummary('exec/1').subscribe(value => { correlation = value.correlationId; });
    const request = http.expectOne('http://localhost:8000/imports/exec%2F1/result-summary');
    expect(request.request.method).toBe('GET');
    request.flush({ summary_status: 'unavailable', summary: null }, { headers: { 'x-correlation-id': 'corr-summary' } });
    expect(correlation).toBe('corr-summary');
  });

  it('pages diagnostics with severity and exports all rows of the same filter', () => {
    service.issues('exec/1', 3, 'warning').subscribe();
    const request = http.expectOne(req => req.url.endsWith('/imports/exec%2F1/issues'));
    expect(request.request.params.get('page')).toBe('3');
    expect(request.request.params.get('page_size')).toBe('20');
    expect(request.request.params.get('severity')).toBe('warning');
    request.flush({});
    service.issuesCsv('exec/1', 'warning').subscribe();
    const download = http.expectOne(req => req.url.endsWith('/imports/exec%2F1/issues/export'));
    expect(download.request.method).toBe('GET');
    expect(download.request.params.get('severity')).toBe('warning');
    expect(download.request.params.has('page')).toBeFalse();
    expect(download.request.responseType).toBe('blob');
    download.flush(new Blob(['id\r\n1\r\n']));
  });

  it('uses encoded execution identifiers in tracking requests', () => {
    service.get('exec/unsafe').subscribe();
    const request = http.expectOne('http://localhost:8000/imports/exec%2Funsafe');
    expect(request.request.method).toBe('GET');
    request.flush({});
  });
});
