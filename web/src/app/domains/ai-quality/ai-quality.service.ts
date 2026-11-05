import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { TranslationKey } from '../../shared/i18n/i18n.models';

export interface FactValue { state: string; value?: string | number | boolean; }
export interface QualityOccurrence {
  evidence_id: string; severity: string; reason: string;
  field: FactValue; column: FactValue; row: FactValue; sheet: FactValue;
  known_value: FactValue; unknown_value: FactValue;
}
export interface QualityGroup { code: string; category: string; causal_evidence: string; occurrences: QualityOccurrence[]; }
export interface QualityText { explanation: string; human_checks: string[]; }
export interface QualityScenario { id: string; groups: QualityGroup[]; baseline: QualityText[]; }
export interface QualityCatalog { schema_version: string; scenarios: QualityScenario[]; }
export interface QualityExplanation {
  group: QualityGroup; text: QualityText; origin: 'model' | 'deterministic';
  state: 'accepted_explanation' | 'fallback_deterministic' | 'insufficient_evidence';
  rejection_code?: string | null; response_sha256?: string | null; elapsed_ms: number;
}
export interface QualityResponse { scenario_id: string; mode: 'model' | 'baseline'; model: string; groups: QualityExplanation[]; }
export const scenarioNames: Record<string, TranslationKey> = {
  'QE-A01': 'quality.scenarioMissing', 'QE-A02': 'quality.scenarioDuplicates',
  'QE-A03': 'quality.scenarioQuantity', 'QE-A04': 'quality.scenarioReference',
  'QD3-E01': 'quality.scenarioClean', 'QD3-E02': 'quality.scenarioMultiple'
};

@Injectable({ providedIn: 'root' })
export class AiQualityService {
  private readonly http = inject(HttpClient);
  catalog(): Observable<QualityCatalog> { return this.http.get<QualityCatalog>(`${environment.apiUrl}/ai/quality/scenarios`); }
  generate(id: string): Observable<QualityResponse> {
    return this.http.post<QualityResponse>(`${environment.apiUrl}/ai/quality/scenarios/${encodeURIComponent(id)}/explanations`, { mode: 'model' });
  }
}
