import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { environment } from '../../../environments/environment';
import { FeedbackService } from './feedback.service';

describe('FeedbackService HTTP contracts', () => {
  let service: FeedbackService; let http: HttpTestingController;
  beforeEach(() => { TestBed.configureTestingModule({providers:[provideHttpClient(),provideHttpClientTesting()]});service=TestBed.inject(FeedbackService);http=TestBed.inject(HttpTestingController); });
  afterEach(() => http.verify());
  it('sends only entered fields and the allowed functional identifier', () => {
    const payload={kind:'bug' as const,title:'Synthetic title',description:'Synthetic description',source_id:'profile'};
    service.create(payload).subscribe();
    const request=http.expectOne(environment.apiUrl+'/feedback');
    expect(request.request.method).toBe('POST');expect(request.request.body).toEqual(payload);request.flush({});
  });
  it('uses the triage API with explicit filters and bounded pagination', () => {
    service.list(true,2,{kind:'suggestion',state:'planned'}).subscribe();
    const request=http.expectOne(r=>r.url===environment.apiUrl+'/feedback/triage');
    expect(request.request.params.get('kind')).toBe('suggestion');expect(request.request.params.get('page')).toBe('2');expect(request.request.params.get('page_size')).toBe('20');request.flush({});
  });
});
