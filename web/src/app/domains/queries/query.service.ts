import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiClient } from '../../shared/api/api-client.service';
import { ConsolidatedWorkorder, Lot, OperationalEntityType, OperationalSearchPage, OperationalSort, PendingItem, Serial } from './query.models';

@Injectable({ providedIn: 'root' })
export class QueryService {
  private readonly api = inject(ApiClient);

  search(type: OperationalEntityType, query: string, page: number, pageSize: number, sort: OperationalSort): Observable<OperationalSearchPage> {
    return this.api.get<OperationalSearchPage>('search', { page, pageSize, sort, filters: { type, query } });
  }

  workorder(number: string, executionId?: string): Observable<ConsolidatedWorkorder> {
    return this.api.get<ConsolidatedWorkorder>(`workorders/${encodeURIComponent(number)}/consolidated-result`, { filters: { execution_id: executionId } });
  }

  lot(number: string, executionId?: string): Observable<Lot> { return this.api.get<Lot>(`lots/${encodeURIComponent(number)}`, { filters: { execution_id: executionId } }); }
  serial(number: string, executionId?: string): Observable<Serial> { return this.api.get<Serial>(`serials/${encodeURIComponent(number)}`, { filters: { execution_id: executionId } }); }
  pending(id: number): Observable<PendingItem> { return this.api.get<PendingItem>(`pending-items/${id}`); }
}
