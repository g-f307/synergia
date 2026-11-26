import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiClient } from '../../shared/api/api-client.service';
import { IndicatorRelatedPage, Indicators } from '../../shared/api/operational.models';
import { ExecutionScopeFilters } from '../executions/execution.models';
import { normalizedExecutionFilters } from '../executions/execution-presentation';
import { I18nService } from '../../shared/i18n/i18n.service';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = inject(ApiClient);
  private readonly i18n = inject(I18nService);

  getIndicators(filters: ExecutionScopeFilters = {}): Observable<Indicators> {
    return this.api.get<Indicators>('indicators', { filters: this.scopeParams(filters) });
  }

  getRelated(entity: 'executions' | 'workorders' | 'pending-items', filters: ExecutionScopeFilters & { page?: number; view?: 'current' | 'history' }): Observable<IndicatorRelatedPage> {
    return this.api.get<IndicatorRelatedPage>(`indicators/${entity}`, {
      page: filters.page, pageSize: 25,
      filters: { ...this.scopeParams(filters), ...(entity === 'workorders' ? { view: filters.view ?? 'current' } : {}) }
    });
  }
  private scopeParams(value: ExecutionScopeFilters): Record<string, string | undefined> {
    const filters = normalizedExecutionFilters(value, this.i18n.timezone());
    return { organization_id: filters.organizationId, source: filters.source, file_type: filters.fileType, started_from: filters.dateFrom, started_to: filters.dateTo, status: filters.status, lifecycle: filters.lifecycle, outcome: filters.outcome, execution_id: filters.executionId };
  }
}
