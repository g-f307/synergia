import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { QueryOptions } from './operational.models';

@Injectable({ providedIn: 'root' })
export class ApiClient {
  private readonly http = inject(HttpClient);

  get<T>(path: string, options: QueryOptions = {}): Observable<T> {
    return this.http.get<T>(this.url(path), { params: this.params(options) });
  }
  post<T>(path: string, body: unknown): Observable<T> { return this.http.post<T>(this.url(path), body); }
  patch<T>(path: string, body: unknown): Observable<T> { return this.http.patch<T>(this.url(path), body); }

  private url(path: string): string { return `${environment.apiUrl}/${path.replace(/^\/+/, '')}`; }
  private params(options: QueryOptions): HttpParams {
    let params = new HttpParams();
    if (options.page !== undefined) params = params.set('page', options.page);
    if (options.pageSize !== undefined) params = params.set('page_size', options.pageSize);
    if (options.sort) params = params.set('sort', options.sort);
    for (const [key, value] of Object.entries(options.filters ?? {})) if (value !== null && value !== undefined && value !== '') params = params.set(key, String(value));
    return params;
  }
}
