import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { I18nService } from '../i18n/i18n.service';
import { ApiErrorKind, ApiFailure } from './api-error';

const kinds: Record<number, ApiErrorKind> = { 401: 'unauthorized', 403: 'forbidden', 404: 'not-found', 409: 'conflict', 422: 'validation' };

export const apiErrorInterceptor: HttpInterceptorFn = (request, next) => {
  const i18n = inject(I18nService);
  return next(request).pipe(catchError((error: HttpErrorResponse) => {
    const body = typeof error.error === 'object' && error.error ? error.error : {};
    const status = error.status;
    const failure: ApiFailure = {
      kind: kinds[status] ?? (status === 0 || status >= 500 ? 'unavailable' : 'internal'),
      status,
      code: String(body.error?.code ?? body.code ?? 'unexpected_error'),
      message: i18n.t(status >= 500 || status === 0 ? 'error.unavailable' : 'error.generic'),
      correlationId: error.headers.get('x-correlation-id') ?? body.correlation_id ?? null,
      fields: Array.isArray(body.error?.fields) ? body.error.fields : []
    };
    return throwError(() => failure);
  }));
};
