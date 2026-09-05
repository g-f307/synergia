import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiClient } from '../../shared/api/api-client.service';
import { PendingFilters, PendingItem, PendingPage } from './pending.models';

@Injectable({ providedIn: 'root' })
export class PendingService {
  private readonly api = inject(ApiClient);

  list(filters: PendingFilters): Observable<PendingPage> {
    return this.api.get<PendingPage>('pending-items', {
      page: filters.page,
      pageSize: filters.pageSize,
      sort: filters.sort,
      filters: {
        status: filters.status,
        category: filters.category,
        priority: filters.priority,
        responsible_area: filters.responsibleArea,
        workorder_number: filters.workorderNumber,
        lot_number: filters.lotNumber,
        serial_number: filters.serialNumber,
        execution_id: filters.executionId
      }
    });
  }

  detail(id: number): Observable<PendingItem> {
    return this.api.get<PendingItem>(`pending-items/${id}`);
  }
}
