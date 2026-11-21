import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, forkJoin, map } from 'rxjs';
import { environment } from '../../../environments/environment';
import { Classification, Divergence, Evidence, Execution, ExecutionAggregate, ExecutionCatalogFilters, ExecutionCatalogPage, ExecutionFrame, ExecutionScopeFilters, Page, PendingItem, ReprocessResult } from './execution.models';
import { I18nService } from '../../shared/i18n/i18n.service';
import { hasExecutionAggregate, normalizedExecutionFilters } from './execution-presentation';

@Injectable({ providedIn: 'root' })
export class ExecutionService {
  private readonly http = inject(HttpClient);
  private readonly i18n = inject(I18nService);
  private readonly base = `${environment.apiUrl}/executions`;
  list(filters: ExecutionCatalogFilters): Observable<ExecutionCatalogPage> {
    const params = this.scopeParams(filters).set('page', filters.page).set('page_size', filters.pageSize).set('sort', filters.sort);
    return this.http.get<ExecutionCatalogPage>(this.base, { params });
  }
  summary(filters: ExecutionScopeFilters = {}): Observable<ExecutionAggregate> {
    return this.http.get<ExecutionAggregate>(`${this.base}/summary`, { params: this.scopeParams(filters) });
  }
  frame(filters: ExecutionCatalogFilters): Observable<ExecutionFrame> {
    return forkJoin({ page: this.list(filters), summary: this.summary(filters) }).pipe(map(frame => {
      if (!hasExecutionAggregate(frame.summary)) {
        throw { kind: 'unavailable', status: 503, code: 'invalid_execution_summary', message: '', correlationId: null, fields: [] };
      }
      return frame;
    }));
  }
  get(id: string): Observable<Execution> { return this.http.get<Execution>(`${this.base}/${encodeURIComponent(id)}`); }
  divergences(id: string, page: number, severity = '', source = '', reference = ''): Observable<Page<Divergence>> {
    let params = new HttpParams().set('page', page).set('page_size', 20).set('sort', 'oldest');
    if (severity) params = params.set('severity', severity);
    if (source) params = params.set('source', source);
    if (/^DIV-[a-f0-9]{32}$/.test(reference)) params = params.set('reference', reference);
    return this.http.get<Page<Divergence>>(`${this.base}/${encodeURIComponent(id)}/divergences`, { params });
  }
  classifications(id: string, page: number, reference = ''): Observable<Page<Classification>> { return this.page(`${this.base}/${encodeURIComponent(id)}/classifications`, page, reference, 'CLA'); }
  pending(id: string, page: number, reference = ''): Observable<Page<PendingItem>> { return this.page(`${this.base}/${encodeURIComponent(id)}/pending-items`, page, reference, 'PEN'); }
  evidences(id: string, page: number, reference = ''): Observable<Page<Evidence>> { return this.page(`${this.base}/${encodeURIComponent(id)}/evidences`, page, reference, 'EVI'); }
  download(id: string, evidenceId: number): Observable<Blob> { return this.http.get(`${this.base}/${encodeURIComponent(id)}/evidences/${evidenceId}/download`, { responseType: 'blob' }); }
  reprocess(id: string, technicalOrigin: string): Observable<ReprocessResult> { return this.http.post<ReprocessResult>(`${this.base}/${encodeURIComponent(id)}/reprocess`, { technical_origin: technicalOrigin, idempotency_key: crypto.randomUUID() }); }
  private scopeParams(value: ExecutionScopeFilters): HttpParams {
    const filters = normalizedExecutionFilters(value, this.i18n.timezone());
    let params = new HttpParams();
    const optional = { organization_id: filters.organizationId, status: filters.status, lifecycle: filters.lifecycle, outcome: filters.outcome, source: filters.source, file_type: filters.fileType, date_from: filters.dateFrom, date_to: filters.dateTo, execution_id: filters.executionId };
    for (const [key, value] of Object.entries(optional)) if (value) params = params.set(key, value);
    return params;
  }
  private page<T>(url: string, page: number, reference = '', prefix = ''): Observable<Page<T>> {
    let params = new HttpParams().set('page', page).set('page_size', 20).set('sort', 'oldest');
    if (prefix && new RegExp(`^${prefix}-[a-f0-9]{32}$`).test(reference)) params = params.set('reference', reference);
    return this.http.get<Page<T>>(url, { params });
  }
}
