import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ExecutionService } from './execution.service';

describe('ExecutionService', () => {
  let service: ExecutionService; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting()]});service=TestBed.inject(ExecutionService);http=TestBed.inject(HttpTestingController); });
  afterEach(()=>http.verify());
  it('encodes execution identifiers and preserves divergence filters',()=>{service.divergences('exec/1',2,'warning','N-FP').subscribe();const request=http.expectOne(value=>value.url.endsWith('/executions/exec%2F1/divergences'));expect(request.request.params.get('page')).toBe('2');expect(request.request.params.get('severity')).toBe('warning');expect(request.request.params.get('source')).toBe('N-FP');request.flush({items:[],pagination:{page:2,page_size:20,total:0,pages:0},sort:'oldest'});});
  it('requests reprocessing with a technical origin and idempotency key',()=>{service.reprocess('exec-1','web-monitor').subscribe();const request=http.expectOne(value=>value.url.endsWith('/executions/exec-1/reprocess'));expect(request.request.method).toBe('POST');expect(request.request.body.technical_origin).toBe('web-monitor');expect(request.request.body.idempotency_key).toBeTruthy();request.flush({execution_id:'exec-2',status:'reprocessing',attempt:2,reprocessed_from_execution_id:'exec-1',previous_execution_id:'exec-1',idempotent_replay:false});});
  it('downloads evidence as a blob through the authenticated HTTP client',()=>{service.download('exec-1',7).subscribe();const request=http.expectOne(value=>value.url.endsWith('/executions/exec-1/evidences/7/download'));expect(request.request.responseType).toBe('blob');request.flush(new Blob(['safe']));});
});
