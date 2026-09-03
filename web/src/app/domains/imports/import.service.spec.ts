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

  it('uses encoded execution identifiers in tracking requests', () => {
    service.get('exec/unsafe').subscribe();
    const request = http.expectOne('http://localhost:8000/imports/exec%2Funsafe');
    expect(request.request.method).toBe('GET');
    request.flush({});
  });
});
