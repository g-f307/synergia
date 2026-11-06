import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { AiQualityService } from './ai-quality.service';

describe('AiQualityService', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] }));
  afterEach(() => TestBed.inject(HttpTestingController).verify());
  it('fetches the synthetic catalog and sends only scenario and generation mode', () => {
    const api = TestBed.inject(AiQualityService), http = TestBed.inject(HttpTestingController);
    api.catalog().subscribe(); http.expectOne('http://localhost:8000/ai/quality/scenarios').flush({ scenarios: [] });
    api.generate('QE-A01').subscribe();
    const request = http.expectOne('http://localhost:8000/ai/quality/scenarios/QE-A01/explanations');
    expect(request.request.method).toBe('POST'); expect(request.request.body).toEqual({ mode: 'model' });
    request.flush({ groups: [] });
  });
});
