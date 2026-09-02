import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { catchError, throwError } from 'rxjs';

import { ApiErrorKind, ApiFailure } from './api-error';

const kinds: Record<number, ApiErrorKind> = { 401: 'unauthorized', 403: 'forbidden', 404: 'not-found', 409: 'conflict', 422: 'validation' };

export const apiErrorInterceptor: HttpInterceptorFn = (request, next) => next(request).pipe(
  catchError((error: HttpErrorResponse) => {
    const body = typeof error.error === 'object' && error.error ? error.error : {};
    const status = error.status;
    const failure: ApiFailure = {
      kind: kinds[status] ?? (status === 0 || status >= 500 ? 'unavailable' : 'internal'),
      status,
      code: String(body.error?.code ?? body.code ?? 'unexpected_error'),
      message: status >= 500 || status === 0 ? 'Serviço temporariamente indisponível.' : String(body.error?.message ?? body.message ?? 'Não foi possível concluir a operação.'),
      correlationId: error.headers.get('x-correlation-id') ?? body.correlation_id ?? null,
      fields: Array.isArray(body.error?.fields) ? body.error.fields : []
    };
    return throwError(() => failure);
  })
);
