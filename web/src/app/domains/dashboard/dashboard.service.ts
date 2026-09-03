import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiClient } from '../../shared/api/api-client.service';
import { Indicators } from '../../shared/api/operational.models';

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly api = inject(ApiClient);

  getIndicators(filters: { organizationId?: string; dateFrom?: string; dateTo?: string } = {}): Observable<Indicators> {
    return this.api.get<Indicators>('indicators', { filters: {
      organization_id: filters.organizationId,
      date_from: filters.dateFrom,
      date_to: filters.dateTo
    } });
  }

  getRelated(entity: 'executions' | 'workorders' | 'pending-items', filters: { organizationId?: string; dateFrom?: string; dateTo?: string; page?: number }): Observable<{ items: Array<{ identifier: string; status: string; occurred_at: string; workorder_number?: string }>; pagination: { page: number; pages: number; total: number }; entity: string }> {
    return this.api.get<{ items: Array<{ identifier: string; status: string; occurred_at: string; workorder_number?: string }>; pagination: { page: number; pages: number; total: number }; entity: string }>(`indicators/${entity}`, { page: filters.page, pageSize: 25, filters: {
      organization_id: filters.organizationId, date_from: filters.dateFrom, date_to: filters.dateTo
    } });
  }
}
