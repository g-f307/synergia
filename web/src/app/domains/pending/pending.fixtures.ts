import { PendingItem, PendingPage } from './pending.models';

export function pendingItem(changes: Partial<PendingItem> = {}): PendingItem {
  return { id: 1, execution_id: 'exec-1', workorder_number: 'WO-001', lot_number: 'LOT-001', serial_number: 'SER-001', category: 'pre_release_pending', reason: 'Synthetic', status: 'open', priority_score: 80, priority: 'high', responsible_area: 'Quality', classification_id: 'class-1', rule_id: 'pre_release_pending', rule_catalog_version: '1.0.0', evidence: { source: 'synthetic' }, created_at: '2026-09-04T12:00:00Z', updated_at: '2026-09-04T12:00:00Z', ...changes };
}

export function pendingPage(items: PendingItem[]): PendingPage {
  return { items, pagination: { page: 1, page_size: 25, total: items.length, pages: items.length ? 1 : 0 }, sort: 'oldest', generated_at: '2026-09-04T12:00:00Z' };
}
