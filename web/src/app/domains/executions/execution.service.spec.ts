import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ExecutionService } from './execution.service';
import { executionAggregate } from '../../../testing/execution-fixtures';
import { ExecutionFrame } from './execution.models';

describe('ExecutionService', () => {
  let service: ExecutionService; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting()]});service=TestBed.inject(ExecutionService);http=TestBed.inject(HttpTestingController); });
  afterEach(()=>http.verify());
  it('publishes a frame only after page and full aggregate are both available', () => {
    const received: ExecutionFrame[] = [];
    service.frame({ outcome: 'skipped_duplicate', source: 'OWM', dateFrom: '2026-11-01T08:00:00-04:00', dateTo: '2026-11-01T12:00:00.999999Z', page: 1, pageSize: 1, sort: 'newest' }).subscribe(frame => received.push(frame));
    const page = http.expectOne(request => request.url.endsWith('/executions'));
    const summary = http.expectOne(request => request.url.endsWith('/executions/summary'));
    expect(page.request.params.get('date_from')).toBe(summary.request.params.get('date_from'));
    expect(summary.request.params.get('date_to')).toBe('2026-11-01T12:00:00.999999Z');
    expect(summary.request.params.get('outcome')).toBe('skipped_duplicate');
    expect(summary.request.params.has('page')).toBeFalse();
    page.flush({ items: [], pagination: { page: 1, page_size: 1, total: 60, pages: 60 }, generated_at: '2026-11-01T12:00:00Z', sort: 'newest' });
    expect(received.length).toBe(0);
    summary.flush(executionAggregate({ skipped_duplicate: 60 }));
    expect(received.length).toBe(1);
    expect(received[0].summary.total).toBe(60);
  });
  it('rejects an incomplete aggregate instead of inventing page totals', () => {
    const received: ExecutionFrame[] = [];
    let failed = false;
    service.frame({ page: 1, pageSize: 25, sort: 'newest' }).subscribe({ next: frame => received.push(frame), error: () => { failed = true; } });
    http.expectOne(request => request.url.endsWith('/executions')).flush({ items: [], pagination: { total: 14 } });
    http.expectOne(request => request.url.endsWith('/summary')).flush({ total: 14, by_outcome: { completed: 3 } });
    expect(failed).toBeTrue(); expect(received.length).toBe(0);
  });
  it('lists executions with stable paging and combined filters',()=>{const dateFrom='2026-09-01T00:00';const dateTo='2026-09-02T00:00';service.list({organizationId:'org-1',status:'completed',lifecycle:'completed',source:'OWM',fileType:'csv',dateFrom,dateTo,executionId:'exec-1',page:2,pageSize:20,sort:'newest'}).subscribe();const request=http.expectOne(value=>value.url.endsWith('/executions'));expect(request.request.params.get('organization_id')).toBe('org-1');expect(request.request.params.get('lifecycle')).toBe('completed');expect(request.request.params.get('execution_id')).toBe('exec-1');expect(request.request.params.get('date_from')).toBe('2026-09-01T04:00:00Z');expect(request.request.params.get('date_to')).toBe('2026-09-02T04:00:00Z');expect(request.request.params.get('page')).toBe('2');expect(request.request.params.get('sort')).toBe('newest');request.flush({items:[],pagination:{page:2,page_size:20,total:0,pages:0},sort:'newest'});});
  it('encodes execution identifiers and preserves divergence filters',()=>{service.divergences('exec/1',2,'warning','N-FP').subscribe();const request=http.expectOne(value=>value.url.endsWith('/executions/exec%2F1/divergences'));expect(request.request.params.get('page')).toBe('2');expect(request.request.params.get('severity')).toBe('warning');expect(request.request.params.get('source')).toBe('N-FP');request.flush({items:[],pagination:{page:2,page_size:20,total:0,pages:0},sort:'oldest'});});
  it('requests reprocessing with a technical origin and idempotency key',()=>{service.reprocess('exec-1','web-monitor').subscribe();const request=http.expectOne(value=>value.url.endsWith('/executions/exec-1/reprocess'));expect(request.request.method).toBe('POST');expect(request.request.body.technical_origin).toBe('web-monitor');expect(request.request.body.idempotency_key).toBeTruthy();request.flush({execution_id:'exec-2',status:'reprocessing',attempt:2,reprocessed_from_execution_id:'exec-1',previous_execution_id:'exec-1',idempotent_replay:false});});
  it('downloads evidence as a blob through the authenticated HTTP client',()=>{service.download('exec-1',7).subscribe();const request=http.expectOne(value=>value.url.endsWith('/executions/exec-1/evidences/7/download'));expect(request.request.responseType).toBe('blob');request.flush(new Blob(['safe']));});
});
