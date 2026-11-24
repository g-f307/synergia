import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiClient } from '../../shared/api/api-client.service';
import { Indicators } from '../../shared/api/operational.models';
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

  getRelated(entity: 'executions' | 'workorders' | 'pending-items', filters: ExecutionScopeFilters & { page?: number }): Observable<{ items: Array<{ identifier: string; status: string; occurred_at: string; workorder_number?: string; execution_id?: string; organization_id?: string; snapshot_id?: number; updated_at?: string }>; pagination: { page: number; pages: number; total: number }; entity: string }> {
    return this.api.get<{ items: Array<{ identifier: string; status: string; occurred_at: string; workorder_number?: string; execution_id?: string; organization_id?: string; snapshot_id?: number; updated_at?: string }>; pagination: { page: number; pages: number; total: number }; entity: string }>(`indicators/${entity}`, { page: filters.page, pageSize: 25, filters: this.scopeParams(filters) });
  }
  private scopeParams(value: ExecutionScopeFilters): Record<string, string | undefined> {
    const filters = normalizedExecutionFilters(value, this.i18n.timezone());
    return { organization_id: filters.organizationId, source: filters.source, file_type: filters.fileType, started_from: filters.dateFrom, started_to: filters.dateTo, status: filters.status, lifecycle: filters.lifecycle, outcome: filters.outcome, execution_id: filters.executionId };
  }
}
