import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';

import { environment } from '../../environments/environment';
import { SessionService } from './session.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const session = inject(SessionService);
  const router = inject(Router);
  const isAuthRequest = request.url.startsWith(`${environment.apiUrl}/auth/`);
  const token = session.accessToken();
  const authorized = token && !isAuthRequest
    ? request.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : request;

  return next(authorized).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401 || isAuthRequest) return throwError(() => error);
      if (session.state() === 'loading') {
        session.clear('expired');
        void router.navigateByUrl('/login');
        return throwError(() => error);
      }
      return session.refresh().pipe(
        switchMap((refreshed) => {
          const newToken = session.accessToken();
          if (!refreshed || !newToken) {
            void router.navigateByUrl('/login');
            return throwError(() => error);
          }
          return next(request.clone({
            setHeaders: { Authorization: `Bearer ${newToken}` }
          }));
        })
      );
    })
  );
};
