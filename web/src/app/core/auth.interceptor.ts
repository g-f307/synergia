import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { SessionService } from './session.service';
import { safeReturnUrl } from './auth-navigation';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const session = inject(SessionService);
  const router = inject(Router);
  const isAuthRequest = [
    `${environment.apiUrl}/auth/login`,
    `${environment.apiUrl}/auth/refresh`
  ].includes(request.url);
  const isProfileBootstrap = request.url === `${environment.apiUrl}/me`
    && session.state() === 'loading';
  const token = session.accessToken();
  const authorized = token && !isAuthRequest
    ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : request;

  return next(authorized).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401 || isAuthRequest || isProfileBootstrap) {
        return throwError(() => error);
      }
      const canReplay = ['GET', 'HEAD', 'OPTIONS'].includes(request.method);
      return session.refresh().pipe(
        switchMap((refreshed) => {
          const newToken = session.accessToken();
          if (!refreshed || !newToken) {
            const returnUrl = safeReturnUrl(router.url);
            void router.navigate(['/login'], { queryParams: { returnUrl } });
            return throwError(() => error);
          }
          if (!canReplay) return throwError(() => error);
          return next(request.clone({
            setHeaders: { Authorization: `Bearer ${newToken}` }
          }));
        })
      );
    })
  );
};
