import { HttpClient, HttpEventType, HttpParams, HttpRequest } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, filter, map } from 'rxjs';

import { environment } from '../../../environments/environment';
import { FileInspection, ImportIssuePage, ImportIssueSeverity, ImportResultSummary, ImportSource, ImportStatus, PipelineSummary, UploadConfiguration, UploadUpdate } from './import.models';

@Injectable({ providedIn: 'root' })
export class ImportService {
  private readonly http = inject(HttpClient);

  policy(): Observable<UploadConfiguration> {
    return this.http.get<UploadConfiguration>(`${environment.apiUrl}/imports/policy`);
  }

  upload(source: ImportSource, file: File, organizationId?: string): Observable<UploadUpdate> {
    const body = new FormData();
    body.append('source', source);
    body.append('file', file, file.name);
    if (organizationId) body.append('organization_id', organizationId);
    const request = new HttpRequest('POST', `${environment.apiUrl}/imports`, body, {
      reportProgress: true
    });
    return this.http.request<ImportStatus>(request).pipe(
      filter((event) => event.type === HttpEventType.UploadProgress || event.type === HttpEventType.Response),
      map((event) => event.type === HttpEventType.Response
        ? { kind: 'complete', result: event.body as ImportStatus }
        : { kind: 'progress', progress: event.total ? Math.round(100 * event.loaded / event.total) : null })
    );
  }

  get(executionId: string): Observable<ImportStatus> {
    return this.http.get<ImportStatus>(`${environment.apiUrl}/imports/${encodeURIComponent(executionId)}`);
  }

  inspections(executionId: string): Observable<FileInspection[]> {
    return this.http.get<FileInspection[]>(`${environment.apiUrl}/imports/${encodeURIComponent(executionId)}/inspections`);
  }

  summary(executionId: string): Observable<PipelineSummary> {
    return this.http.get<PipelineSummary>(`${environment.apiUrl}/imports/${encodeURIComponent(executionId)}/pipeline-summary`);
  }

  resultSummary(executionId: string): Observable<ImportResultSummary> {
    return this.http.get<ImportResultSummary>(`${environment.apiUrl}/imports/${encodeURIComponent(executionId)}/result-summary`, { observe: 'response' }).pipe(
      map((response) => ({ ...response.body!, correlationId: response.headers.get('x-correlation-id') }))
    );
  }

  issues(executionId: string, page = 1, severity: ImportIssueSeverity | '' = ''): Observable<ImportIssuePage> {
    let params = new HttpParams().set('page', page).set('page_size', 20).set('sort', 'oldest');
    if (severity) params = params.set('severity', severity);
    return this.http.get<ImportIssuePage>(`${environment.apiUrl}/imports/${encodeURIComponent(executionId)}/issues`, { params });
  }

  issuesCsv(executionId: string, severity: ImportIssueSeverity | '' = ''): Observable<Blob> {
    let params = new HttpParams().set('sort', 'oldest');
    if (severity) params = params.set('severity', severity);
    return this.http.get(`${environment.apiUrl}/imports/${encodeURIComponent(executionId)}/issues/export`, { params, responseType: 'blob' });
  }
}
