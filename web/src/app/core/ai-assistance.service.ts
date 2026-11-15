import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

export interface AiAssistanceFinding {
  title: string;
  explanation: string;
  evidence_refs: string[];
}

export interface AiAssistanceResponse {
  assistance_id: string;
  execution_id: string;
  state: 'ready' | 'insufficient_evidence' | 'unavailable' | 'rejected';
  summary: string;
  findings: AiAssistanceFinding[];
  human_checks: string[];
  limitations: string[];
  provenance: {
    contract_version: '1.0.0';
    model: string | null;
    digest: string | null;
    context_hash: string;
    prompt_hash: string;
    origin: 'model' | 'deterministic';
    timings: { context_ms: number; generation_ms: number; total_ms: number };
  };
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class AiAssistanceService {
  private readonly http = inject(HttpClient);

  generate(executionId: string): Observable<AiAssistanceResponse> {
    return this.http.post<AiAssistanceResponse>(this.url(executionId), {});
  }

  latest(executionId: string): Observable<AiAssistanceResponse> {
    return this.http.get<AiAssistanceResponse>(`${this.url(executionId)}/latest`);
  }

  private url(executionId: string): string {
    return `${environment.apiUrl}/executions/${encodeURIComponent(executionId)}/ai-assistance`;
  }
}
