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

  for (const status of [401, 403, 404, 503]) {
    it(`decodes bounded JSON download errors without leaking messages (HTTP ${status})`, async () => {
      const received = new Promise<ApiFailure>(resolve => http.get('/download', { responseType: 'blob' }).subscribe({ error: resolve }));
      controller.expectOne('/download').flush(
        new Blob([JSON.stringify({ error: { code: 'import_issues_unavailable', message: '/private password=synthetic', details: { storage_path: '/private' } } })], { type: 'application/json' }),
        { status, statusText: 'Synthetic', headers: { 'x-correlation-id': 'corr-download' } }
      );
      const failure = await received;
      expect(failure.status).toBe(status); expect(failure.code).toBe('import_issues_unavailable');
      expect(failure.correlationId).toBe('corr-download');
      expect(failure.message).not.toContain('private'); expect(failure.details).toEqual({});
    });
  }

  it('falls back safely for a malformed JSON download error', async () => {
    const received = new Promise<ApiFailure>(resolve => http.get('/download', { responseType: 'blob' }).subscribe({ error: resolve }));
    controller.expectOne('/download').flush(new Blob(['not json /private'], { type: 'application/json' }), { status: 503, statusText: 'Synthetic' });
    const failure = await received;
    expect(failure.kind).toBe('unavailable'); expect(failure.code).toBe('unexpected_error');
    expect(failure.message).not.toContain('private');
  });

  it('preserves safe retry guidance for rate limiting', () => {
    let failure: ApiFailure | undefined;
    http.post('/reports', {}).subscribe({ error: (error: ApiFailure) => { failure = error; } });
    controller.expectOne('/reports').flush(
      { error: { code: 'rate_limit_exceeded', details: { retry_after_seconds: 23, token: 'secret' } } },
      { status: 429, statusText: 'Too Many Requests' }
    );
    expect(failure?.kind).toBe('rate-limited');
    expect(failure?.details).toEqual({ retry_after_seconds: 23 });
  });
});
