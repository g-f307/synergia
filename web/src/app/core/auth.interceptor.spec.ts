import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

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

  it('renews and retries once after an unauthorized response', () => {
    http.get('/protected').subscribe();
    controller.expectOne('/protected').flush(
      {}, { status: 401, statusText: 'Unauthorized' }
    );
    const retry = controller.expectOne('/protected');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer refreshed-token');
    retry.flush({});
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
});
