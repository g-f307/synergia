import type { ExecutionAggregate } from './execution-contract.models';

export interface Page<T> { items: T[]; page: number; page_size: number; total: number; }
export interface ImportSummary { execution_id: string; status: string; created_at: string; errors: number; warnings: number; }
export interface ExecutionSummary { id: string; status: string; original_execution_id: string | null; created_at: string; updated_at: string; }

export type QuantityKey = 'planned' | 'produced' | 'received' | 'released';
export interface QuantityCoverage {
  known_sum: number | null;
  known_count: number;
  total_count: number;
  coverage_percent: number | null;
  state: 'complete' | 'partial' | 'missing' | 'empty';
}
export interface IndicatorScope { permissions: string[]; organization_ids: string[] | null; }
export interface IndicatorRelatedItem {
  identifier: string;
  status: string;
  occurred_at: string;
  workorder_number?: string;
  execution_id?: string;
  organization_id?: string;
  organization_name?: string | null;
  organization_code?: string | null;
  snapshot_id?: number;
  updated_at?: string;
}
export interface IndicatorRelatedPage {
  items: IndicatorRelatedItem[];
  pagination: { page: number; pages: number; total: number };
  entity: string;
  view: 'current' | 'history';
  scope: IndicatorScope;
}

export interface Indicators {
  generated_at: string;
  source: string;
  organizations: Array<{ id: string; code: string; name: string }>;
  filters: { organization_id: string | null; date_from: string | null; date_to: string | null };
  executions: Record<string, number>;
  execution_summary: ExecutionAggregate;
  workorders: { total?: number; partially_released?: number };
  workorders_current: { total: number; partially_released: number };
  quantities_coverage: Record<QuantityKey, QuantityCoverage>;
  pending_items: Record<string, number>;
  quantities: { planned?: number | null; produced?: number | null; received?: number | null; released?: number | null };
}
export interface OperationalEntity { identifier: string; execution_id: string; status: string | null; quantities: Record<string, number | null>; }
export interface PendingItem { id: string; workorder_number: string; category: string; priority: number; status: string; reason: string | null; }
export interface QueryOptions { page?: number; pageSize?: number; sort?: string; filters?: Record<string, string | number | boolean | null | undefined>; }
