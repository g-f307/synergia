export const EXECUTION_OUTCOMES = ['active', 'completed', 'partial', 'skipped_duplicate', 'failed', 'cancelled', 'unknown'] as const;
export type ExecutionOutcome = typeof EXECUTION_OUTCOMES[number];
export type ExecutionOutcomeCounts = Record<ExecutionOutcome, number>;
export interface ExecutionAggregate {
  generated_at: string;
  scope: { permission: 'execution.read' | 'dashboard.read'; organization_ids: string[] | null };
  filters: { organization_id: string | null; source: string | null; file_type: string | null; date_from: string | null; date_to: string | null; status: string | null; lifecycle: string | null; outcome: ExecutionOutcome | null; execution_id: string | null };
  total: number;
  by_outcome: ExecutionOutcomeCounts;
  by_source: Array<{ source: string | null; total: number; by_outcome: ExecutionOutcomeCounts; rows_read: number; latest_started_at: string }>;
}
