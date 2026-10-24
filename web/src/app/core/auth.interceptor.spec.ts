import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Subject, of } from 'rxjs';

import { authInterceptor } from './auth.interceptor';
import { SessionService } from './session.service';

describe('authInterceptor', () => {
  const session = {
    token: 'initial-token',
    state: signal('authenticated'),
    accessToken: () => session.token,
    refresh: () => {
      session.token = 'refreshed-token';
      return of(true);
    },
    clear: jasmine.createSpy('clear')
  };
  let http: HttpClient;
  let controller: HttpTestingController;

  beforeEach(() => {
    session.token = 'initial-token';
    session.state.set('authenticated');
    session.clear.calls.reset();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: SessionService, useValue: session }
      ]
    });
    http = TestBed.inject(HttpClient);
    controller = TestBed.inject(HttpTestingController);
  });

  afterEach(() => controller.verify());

  it('adds the in-memory bearer token', () => {
    http.get('/protected').subscribe();
    const request = controller.expectOne('/protected');
    expect(request.request.headers.get('Authorization')).toBe('Bearer initial-token');
    request.flush({});
  });

  it('authenticates protected session endpoints but not login or refresh', () => {
    http.get('http://localhost:8000/auth/sessions').subscribe();
    const sessions = controller.expectOne('http://localhost:8000/auth/sessions');
    expect(sessions.request.headers.get('Authorization')).toBe('Bearer initial-token');
    sessions.flush({ items: [] });

    http.post('http://localhost:8000/auth/login', {}).subscribe();
    const login = controller.expectOne('http://localhost:8000/auth/login');
    expect(login.request.headers.has('Authorization')).toBeFalse();
    login.flush({});
  });

  it('renews and retries once after an unauthorized response', () => {
    http.get('/protected').subscribe();
    controller.expectOne('/protected').flush(
      {}, { status: 401, statusText: 'Unauthorized' }
    );
    const retry = controller.expectOne('/protected');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer refreshed-token');
    retry.flush({});
  });

  it('joins one refresh when concurrent idempotent requests receive unauthorized responses', () => {
    const refreshResult = new Subject<boolean>();
    const refresh = spyOn(session, 'refresh').and.callFake(() => {
      session.state.set('loading');
      return refreshResult;
    });
    const responses: string[] = [];

    http.get<{ request: string }>('/protected/one').subscribe((value) => responses.push(value.request));
    http.get<{ request: string }>('/protected/two').subscribe((value) => responses.push(value.request));
    controller.expectOne('/protected/one').flush({}, { status: 401, statusText: 'Unauthorized' });
    controller.expectOne('/protected/two').flush({}, { status: 401, statusText: 'Unauthorized' });

    expect(refresh).toHaveBeenCalledTimes(2);
    session.token = 'refreshed-token';
    refreshResult.next(true);
    refreshResult.complete();

    const retries = controller.match((request) => request.url.startsWith('/protected/'));
    expect(retries.length).toBe(2);
    for (const retry of retries) {
      expect(retry.request.headers.get('Authorization')).toBe('Bearer refreshed-token');
      retry.flush({ request: retry.request.url });
    }
    expect(responses).toEqual(['/protected/one', '/protected/two']);
    expect(session.clear).not.toHaveBeenCalled();
  });

  it('preserves forbidden responses without attempting refresh', () => {
    let receivedStatus = 0;
    http.get('/protected').subscribe({
      error: (error) => { receivedStatus = error.status; }
    });
    controller.expectOne('/protected').flush(
      {}, { status: 403, statusText: 'Forbidden' }
    );

    expect(receivedStatus).toBe(403);
    controller.expectNone('http://localhost:8000/auth/refresh');
  });

  it('does not recursively refresh when profile bootstrap rejects the renewed token', () => {
    const refresh = spyOn(session, 'refresh').and.callThrough();
    session.state.set('loading');
    let receivedStatus = 0;

    http.get('http://localhost:8000/me').subscribe({
      error: (error) => { receivedStatus = error.status; }
    });
    controller.expectOne('http://localhost:8000/me').flush(
      {}, { status: 401, statusText: 'Unauthorized' }
    );

    expect(receivedStatus).toBe(401);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('may restore the session but never replays a non-idempotent request', () => {
    const refresh = spyOn(session, 'refresh').and.callThrough();
    let receivedStatus = 0;
    http.post('/protected', { decision: 'approve' }).subscribe({
      error: (error) => { receivedStatus = error.status; }
    });
    controller.expectOne('/protected').flush(
      {}, { status: 401, statusText: 'Unauthorized' }
    );

    expect(receivedStatus).toBe(401);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(session.clear).not.toHaveBeenCalled();
    controller.expectNone('/protected');
  });
});
