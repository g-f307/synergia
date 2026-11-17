import { ExecutionAggregate, ExecutionOutcomeCounts } from '../app/domains/executions/execution.models';

/** Explicit aggregate fixtures; production clients never derive totals from pages. */
export function executionAggregate(counts: Partial<ExecutionOutcomeCounts> = {}, overrides: Partial<ExecutionAggregate> = {}): ExecutionAggregate {
  const by_outcome: ExecutionOutcomeCounts = { active: 0, completed: 0, partial: 0, skipped_duplicate: 0, failed: 0, cancelled: 0, unknown: 0, ...counts };
  const total = Object.values(by_outcome).reduce((sum, value) => sum + value, 0);
  return {
    generated_at: '2026-10-27T03:00:00Z',
    scope: { permission: 'execution.read', organization_ids: ['org-synthetic'] },
    filters: { organization_id: null, source: null, file_type: null, date_from: null, date_to: null, status: null, lifecycle: null, outcome: null, execution_id: null },
    total, by_outcome,
    by_source: total ? [{ source: 'OWM', total, by_outcome, rows_read: 0, latest_started_at: '2026-10-27T02:59:00Z' }] : [],
    ...overrides
  };
}
