import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { map, of, switchMap } from 'rxjs';

import { SessionService } from './session.service';

export const authenticatedGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.ensureSession().pipe(
    map((authenticated) => authenticated || router.createUrlTree(['/login']))
  );
};

export const adminGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);
  return session.ensureSession().pipe(
    switchMap(() => session.profile() ? of(session.profile()!) : session.loadProfile()),
    map(() => session.isAdministrator() || router.createUrlTree(['/profile']))
  );
};

export function permissionGuard(permission: string): CanActivateFn {
  return () => {
    const session = inject(SessionService);
    const router = inject(Router);
    return session.ensureSession().pipe(
      switchMap(() => session.profile() ? of(session.profile()!) : session.loadProfile()),
      map(() => session.hasPermission(permission) || router.createUrlTree(['/profile']))
    );
  };
}
