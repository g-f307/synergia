import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { PendingService } from './pending.service';

describe('PendingService', () => {
  let service: PendingService;let http: HttpTestingController;
  beforeEach(()=>{TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting()]});service=TestBed.inject(PendingService);http=TestBed.inject(HttpTestingController)});afterEach(()=>http.verify());
  it('sends all reproducible queue filters to the API',()=>{service.list({status:'open',category:'oqc_hold',priority:'high',responsibleArea:'Quality',workorderNumber:'',lotNumber:'LOT-01',serialNumber:'',executionId:'',page:2,pageSize:10,sort:'priority'}).subscribe();const request=http.expectOne(candidate=>candidate.url===`${environment.apiUrl}/pending-items`);expect(request.request.params.get('status')).toBe('open');expect(request.request.params.get('lot_number')).toBe('LOT-01');expect(request.request.params.get('responsible_area')).toBe('Quality');expect(request.request.params.get('sort')).toBe('priority');request.flush({items:[],pagination:{page:2,page_size:10,total:0,pages:0},sort:'priority',generated_at:'2026-09-04T12:00:00Z'})});
  it('loads a pending item by its numeric identifier',()=>{service.detail(42).subscribe();const request=http.expectOne(`${environment.apiUrl}/pending-items/42`);expect(request.request.method).toBe('GET');request.flush({})});
});
