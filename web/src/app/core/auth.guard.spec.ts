import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom, of } from 'rxjs';

import { adminGuard, authenticatedGuard, permissionGuard } from './auth.guard';
import { SessionService } from './session.service';

describe('authentication guards', () => {
  const session = {
    authenticated: true,
    administrator: false,
    ensureSession: () => of(session.authenticated),
    profile: signal({ id: 'synthetic' }),
    loadProfile: () => of({ id: 'synthetic' }),
    isAdministrator: () => session.administrator
    ,hasPermission: (key: string) => key === 'import.create'
  };

  beforeEach(() => {
    session.authenticated = true;
    session.administrator = false;
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: SessionService, useValue: session }
      ]
    });
  });

  it('redirects an expired session to login', async () => {
    session.authenticated = false;
    const result = await TestBed.runInInjectionContext(() => firstValueFrom(
      authenticatedGuard({} as never, {} as never) as Observable<boolean | UrlTree>
    ));

    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/login');
  });

  it('blocks the administrative route without global access', async () => {
    const result = await TestBed.runInInjectionContext(() => firstValueFrom(
      adminGuard({} as never, {} as never) as Observable<boolean | UrlTree>
    ));

    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/profile');
  });

  it('allows only routes covered by an effective permission', async () => {
    const allowed = await TestBed.runInInjectionContext(() => firstValueFrom(
      permissionGuard('import.create')({} as never, {} as never) as Observable<boolean | UrlTree>
    ));
    const denied = await TestBed.runInInjectionContext(() => firstValueFrom(
      permissionGuard('import.read')({} as never, {} as never) as Observable<boolean | UrlTree>
    ));
    expect(allowed).toBeTrue();
    expect(TestBed.inject(Router).serializeUrl(denied as UrlTree)).toBe('/profile');
  });
});
