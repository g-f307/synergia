import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ApiFailure } from './api-error';
import { apiErrorInterceptor } from './error.interceptor';
import { I18nService } from '../i18n/i18n.service';

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

  it('localizes safe errors without exposing server-provided messages', () => {
    TestBed.inject(I18nService).configure('en-US');
    let failure: ApiFailure | undefined;
    http.get('/resource').subscribe({ error: (error: ApiFailure) => { failure = error; } });
    controller.expectOne('/resource').flush(
      { error: { code: 'invalid_request', message: 'Mensagem fixa do servidor' } },
      { status: 422, statusText: 'Unprocessable Entity' }
    );

    expect(failure?.code).toBe('invalid_request');
    expect(failure?.message).toBe('The operation could not be completed.');
    expect(failure?.message).not.toContain('servidor');
  });

  it('preserves only structured details needed for a safe duplicate journey', () => {
    let failure: ApiFailure | undefined;
    http.post('/imports', {}).subscribe({ error: (error: ApiFailure) => { failure = error; } });
    controller.expectOne('/imports').flush(
      { error: { code: 'duplicate_file', message: 'Arquivo já importado', details: { execution_id: 'new', duplicate_of_execution_id: 'original', storage_path: '/secret/file' } } },
      { status: 409, statusText: 'Conflict', headers: { 'x-correlation-id': 'corr-409' } }
    );
    expect(failure?.details).toEqual({ execution_id: 'new', duplicate_of_execution_id: 'original' });
    expect(failure?.message).not.toContain('Arquivo');
  });
});
