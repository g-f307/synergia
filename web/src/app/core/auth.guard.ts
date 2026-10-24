import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of, switchMap } from 'rxjs';

import { SessionService } from './session.service';

export const authenticatedGuard: CanActivateFn = (_route, state) => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.ensureSession().pipe(
    map((authenticated) => authenticated || router.createUrlTree(['/login'], {
      queryParams: { returnUrl: state.url }
    }))
  );
};

export const publicOnlyGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.ensureSession().pipe(
    map((authenticated) => authenticated ? router.createUrlTree(['/profile']) : true)
  );
};

export const adminGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.ensureSession().pipe(
    switchMap((authenticated) => authenticated
      ? (session.profile() ? of(session.profile()!) : session.loadProfile())
      : of(null)),
    map((profile) => profile && session.isAdministrator()
      ? true
      : router.createUrlTree(['/profile']))
  );
};

export function permissionGuard(permission: string): CanActivateFn {
  return () => {
    const session = inject(SessionService);
    const router = inject(Router);
    return session.ensureSession().pipe(
      switchMap((authenticated) => authenticated
        ? (session.profile() ? of(session.profile()!) : session.loadProfile())
        : of(null)),
      map((profile) => profile && session.hasPermission(permission)
        ? true
        : router.createUrlTree(['/profile']))
    );
  };
}
