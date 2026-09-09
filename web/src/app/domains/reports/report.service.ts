import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { CreateReportPayload, ReportCatalogQuery, ReportDetail, ReportExportFormat, ReportPage, ReportPolicy, ReportVersion } from './report.models';

@Injectable({ providedIn: 'root' })
export class ReportService {
  private readonly http = inject(HttpClient);
  private readonly base = `${environment.apiUrl}/reports`;

  policy(): Observable<ReportPolicy> { return this.http.get<ReportPolicy>(`${this.base}/policy`); }

  list(query: ReportCatalogQuery): Observable<ReportPage> {
    let params = new HttpParams()
      .set('page', query.page)
      .set('page_size', query.pageSize)
      .set('sort', query.sort);
    if (query.organizationId) params = params.set('organization_id', query.organizationId);
    if (query.reportType) params = params.set('report_type', query.reportType);
    if (query.state) params = params.set('state', query.state);
    if (query.executionId) params = params.set('execution_id', query.executionId);
    return this.http.get<ReportPage>(this.base, { params });
  }

  get(reportId: string, version?: number): Observable<ReportDetail> {
    const id = encodeURIComponent(reportId);
    const suffix = version ? `/versions/${version}` : '';
    return this.http.get<ReportDetail>(`${this.base}/${id}${suffix}`);
  }

  versions(reportId: string, page: number, pageSize: number): Observable<ReportPage> {
    return this.http.get<ReportPage>(`${this.base}/${encodeURIComponent(reportId)}/versions`, {
      params: new HttpParams().set('page', page).set('page_size', pageSize)
    });
  }

  create(payload: CreateReportPayload): Observable<ReportDetail> {
    return this.http.post<ReportDetail>(this.base, payload);
  }

  cancel(reportId: string, version: number, reason: string): Observable<ReportVersion> {
    return this.http.post<ReportVersion>(`${this.base}/${encodeURIComponent(reportId)}/versions/${version}/cancel`, { reason });
  }

  export(reportId: string, version: number, format: ReportExportFormat): Observable<HttpResponse<Blob>> {
    return this.http.get(`${this.base}/${encodeURIComponent(reportId)}/versions/${version}/export`, {
      params: { format }, responseType: 'blob', observe: 'response'
    });
  }
}
