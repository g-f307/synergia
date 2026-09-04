import { ConsolidatedWorkorder, Lot, OperationalSearchPage, Serial } from './query.models';

export const QUERY_STALE_AFTER_MS = 24 * 60 * 60 * 1000;

export function isStale(timestamp: string, now = Date.now()): boolean {
  const reference = Date.parse(timestamp);
  return Number.isFinite(reference) && now - reference > QUERY_STALE_AFTER_MS;
}

export function isSearchPartial(page: OperationalSearchPage): boolean {
  return page.items.some((item) => !item.processing_status || !item.organization_code);
}

export function isWorkorderPartial(result: ConsolidatedWorkorder): boolean {
  const workorder = result.workorder;
  return !workorder.processing_status
    || !workorder.organization_code
    || workorder.partially_released === null
    || result.classifications.some((item) => item.data_quality !== 'complete');
}

export function isEntityPartial(entity: Lot | Serial): boolean {
  const missingContext = !entity.execution_id || !entity.workorder_number;
  if ('serial_number' in entity) {
    return missingContext || !entity.lot_number || !entity.container_number;
  }
  return missingContext || !Array.isArray(entity.serials);
}
