import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { SessionService } from './session.service';
import { UserProfile } from './session.models';

const profile: UserProfile = {
  id: '00000000-0000-4000-8000-000000000001',
  status: 'active',
  display_name: 'Synthetic User',
  emails: [{ email: 'user@example.invalid', is_primary: true, is_verified: true }],
  locale: 'pt-BR',
  timezone: 'America/Manaus',
  notifications: { email: true, in_app: true },
  avatar: null,
  permissions: [{ key: 'access.admin', organizations: null }],
  version: 1
};

describe('SessionService', () => {
  let service: SessionService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([])
      ]
    });
    service = TestBed.inject(SessionService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('keeps the access token in memory and loads the authenticated profile', () => {
    service.login('user@example.invalid', 'synthetic-password').subscribe();
    const login = http.expectOne('http://localhost:8000/auth/login');
    expect(login.request.withCredentials).toBeTrue();
    login.flush({
      access_token: 'memory-only-token',
      token_type: 'Bearer',
      expires_in: 900,
      session_id: '00000000-0000-4000-8000-000000000002'
    });
    http.expectOne('http://localhost:8000/me').flush(profile);

    expect(service.accessToken()).toBe('memory-only-token');
    expect(service.isAuthenticated()).toBeTrue();
    expect(service.isAdministrator()).toBeTrue();
    expect(localStorage.length).toBe(0);
  });

  it('clears local state when refresh expires', () => {
    let refreshed = true;
    service.refresh().subscribe((value) => { refreshed = value; });
    const request = http.expectOne('http://localhost:8000/auth/refresh');
    expect(request.request.withCredentials).toBeTrue();
    request.flush({}, { status: 401, statusText: 'Unauthorized' });

    expect(refreshed).toBeFalse();
    expect(service.state()).toBe('expired');
    expect(service.profile()).toBeNull();
  });
});
