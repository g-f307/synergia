import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApiFailure } from './api-error';
import { apiErrorInterceptor } from './error.interceptor';

describe('apiErrorInterceptor', () => {
  let http: HttpClient;
  let controller: HttpTestingController;
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(withInterceptors([apiErrorInterceptor])), provideHttpClientTesting()] });
    http = TestBed.inject(HttpClient);
    controller = TestBed.inject(HttpTestingController);
  });
  afterEach(() => controller.verify());

  it('keeps forbidden distinct from unavailable and preserves correlation ID', () => {
    let failure: ApiFailure | undefined;
    http.get('/resource').subscribe({ error: (error: ApiFailure) => { failure = error; } });
    controller.expectOne('/resource').flush({ error: { code: 'forbidden', message: 'Negado' } }, { status: 403, statusText: 'Forbidden', headers: { 'x-correlation-id': 'corr-123' } });
    expect(failure?.kind).toBe('forbidden');
    expect(failure?.correlationId).toBe('corr-123');
  });

  it('does not expose internal details for server errors', () => {
    let failure: ApiFailure | undefined;
    http.get('/resource').subscribe({ error: (error: ApiFailure) => { failure = error; } });
    controller.expectOne('/resource').flush({ message: 'SQL password=/secret' }, { status: 500, statusText: 'Error' });
    expect(failure?.kind).toBe('unavailable');
    expect(failure?.message).not.toContain('SQL');
  });
});
