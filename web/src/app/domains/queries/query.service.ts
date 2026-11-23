import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { workorderSelectionParams } from './workorder-selection';
import { ApiClient } from '../../shared/api/api-client.service';
import { ConsolidatedWorkorder, Lot, OperationalEntityType, OperationalSearchPage, OperationalSort, Serial, WorkorderSelection } from './query.models';

@Injectable({ providedIn: 'root' })
export class QueryService {
  private readonly api = inject(ApiClient);

  search(type: OperationalEntityType, query: string, page: number, pageSize: number, sort: OperationalSort, selection: WorkorderSelection = {}): Observable<OperationalSearchPage> {
    return this.api.get<OperationalSearchPage>('search', { page, pageSize, sort, filters: { type, query, ...(type === 'workorder' ? { view: selection.view, ...workorderSelectionParams(selection) } : {}) } });
  }

  workorder(number: string, executionId?: string, selection: WorkorderSelection = {}): Observable<ConsolidatedWorkorder> {
    return this.api.get<ConsolidatedWorkorder>(`workorders/${encodeURIComponent(number)}/consolidated-result`, { filters: { ...workorderSelectionParams(selection), execution_id: executionId ?? selection.executionId } });
  }

  lot(number: string, executionId?: string): Observable<Lot> { return this.api.get<Lot>(`lots/${encodeURIComponent(number)}`, { filters: { execution_id: executionId } }); }
  serial(number: string, executionId?: string): Observable<Serial> { return this.api.get<Serial>(`serials/${encodeURIComponent(number)}`, { filters: { execution_id: executionId } }); }
}
