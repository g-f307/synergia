import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Classification, Divergence, Evidence, Execution, Page, PendingItem, ReprocessResult } from './execution.models';

@Injectable({ providedIn: 'root' })
export class ExecutionService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/executions`;
  get(id: string): Observable<Execution> { return this.http.get<Execution>(`${this.base}/${encodeURIComponent(id)}`); }
  divergences(id: string, page: number, severity = '', source = ''): Observable<Page<Divergence>> {
    let params = new HttpParams().set('page', page).set('page_size', 20).set('sort', 'oldest');
    if (severity) params = params.set('severity', severity);
    if (source) params = params.set('source', source);
    return this.http.get<Page<Divergence>>(`${this.base}/${encodeURIComponent(id)}/divergences`, { params });
  }
  classifications(id: string, page: number): Observable<Page<Classification>> { return this.page(`${this.base}/${encodeURIComponent(id)}/classifications`, page); }
  pending(id: string, page: number): Observable<Page<PendingItem>> { return this.page(`${this.base}/${encodeURIComponent(id)}/pending-items`, page); }
  evidences(id: string, page: number): Observable<Page<Evidence>> { return this.page(`${this.base}/${encodeURIComponent(id)}/evidences`, page); }
  download(id: string, evidenceId: number): Observable<Blob> { return this.http.get(`${this.base}/${encodeURIComponent(id)}/evidences/${evidenceId}/download`, { responseType: 'blob' }); }
  reprocess(id: string, technicalOrigin: string): Observable<ReprocessResult> { return this.http.post<ReprocessResult>(`${this.base}/${encodeURIComponent(id)}/reprocess`, { technical_origin: technicalOrigin, idempotency_key: crypto.randomUUID() }); }
  private page<T>(url: string, page: number): Observable<Page<T>> { return this.http.get<Page<T>>(url, { params: new HttpParams().set('page', page).set('page_size', 20).set('sort', 'oldest') }); }
}
