import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../environments/environment';
import { AiAssistanceService } from './ai-assistance.service';

describe('AiAssistanceService', () => {
  let service: AiAssistanceService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(AiAssistanceService);
    http = TestBed.inject(HttpTestingController);
  });
  afterEach(() => http.verify());

  it('sends an empty body and reads the latest result', () => {
    const url = `${environment.apiUrl}/executions/test-id/ai-assistance`;
    service.generate('test-id').subscribe();
    const generate = http.expectOne(url);
    expect(generate.request.method).toBe('POST');
    expect(generate.request.body).toEqual({});
    generate.flush({});
    service.latest('test-id').subscribe();
    const latest = http.expectOne(`${url}/latest`);
    expect(latest.request.method).toBe('GET');
    latest.flush({});
  });
});
