import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { reportDetail, reportPage, reportPolicy } from './report.fixtures';
import { ReportService } from './report.service';

describe('ReportService', () => {
  let service: ReportService; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }); service = TestBed.inject(ReportService); http = TestBed.inject(HttpTestingController); });
  afterEach(() => http.verify());
  it('sends catalog filters, sorting and pagination to the backend', () => { service.list({ organizationId: 'org-1', reportType: 'oqc_summary', state: 'succeeded', executionId: 'exec-1', sort: 'oldest', page: 2, pageSize: 10 }).subscribe(); const request = http.expectOne((candidate) => candidate.url === `${environment.apiUrl}/reports`); expect(request.request.params.get('organization_id')).toBe('org-1'); expect(request.request.params.get('report_type')).toBe('oqc_summary'); expect(request.request.params.get('state')).toBe('succeeded'); expect(request.request.params.get('execution_id')).toBe('exec-1'); expect(request.request.params.get('sort')).toBe('oldest'); expect(request.request.params.get('page')).toBe('2'); request.flush(reportPage([])); });
  it('uses exact versions and backend-produced exports', () => { service.get('report id', 2).subscribe(); http.expectOne(`${environment.apiUrl}/reports/report%20id/versions/2`).flush(reportDetail({ version: 2 })); service.export('report id', 2, 'csv').subscribe(); const download = http.expectOne((candidate) => candidate.url.endsWith('/reports/report%20id/versions/2/export')); expect(download.request.responseType).toBe('blob'); expect(download.request.params.get('format')).toBe('csv'); download.flush(new Blob(['safe'])); });
  it('loads the contractual policy and creates reports on the server', () => { service.policy().subscribe(); http.expectOne(`${environment.apiUrl}/reports/policy`).flush(reportPolicy()); service.create({ report_type: 'workorder_consolidated', execution_id: 'exec-1', organization_id: 'org-1', reference_at: '2026-09-08T12:00:00Z', filters: {} }).subscribe(); const request = http.expectOne(`${environment.apiUrl}/reports`); expect(request.request.method).toBe('POST'); expect(request.request.body.organization_id).toBe('org-1'); request.flush(reportDetail()); });
});
