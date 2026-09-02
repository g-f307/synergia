import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting
} from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { SessionService } from './session.service';
import { UserProfile } from './session.models';
import { I18nService } from '../shared/i18n/i18n.service';

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
    expect(TestBed.inject(I18nService).locale()).toBe('pt-BR');
    expect(localStorage.length).toBe(0);
  });

  it('applies the persisted locale again after loading a new session', () => {
    service.login('user@example.invalid', 'synthetic-password').subscribe();
    http.expectOne('http://localhost:8000/auth/login').flush({
      access_token: 'memory-only-token',
      token_type: 'Bearer',
      expires_in: 900,
      session_id: '00000000-0000-4000-8000-000000000002'
    });
    http.expectOne('http://localhost:8000/me').flush({ ...profile, locale: 'en-US' });

    expect(TestBed.inject(I18nService).locale()).toBe('en-US');
    expect(service.isAuthenticated()).toBeTrue();
  });

  it('applies a locale change returned by the profile API', () => {
    service.updateProfile({ version: 1, locale: 'en-US' }).subscribe();
    const request = http.expectOne('http://localhost:8000/me');
    expect(request.request.method).toBe('PATCH');
    request.flush({ ...profile, locale: 'en-US' });

    expect(service.profile()?.locale).toBe('en-US');
    expect(TestBed.inject(I18nService).locale()).toBe('en-US');
    expect(document.documentElement.lang).toBe('en-US');
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
