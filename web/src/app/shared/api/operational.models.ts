export interface Page<T> { items: T[]; page: number; page_size: number; total: number; }
export interface ImportSummary { execution_id: string; status: string; created_at: string; errors: number; warnings: number; }
export interface ExecutionSummary { id: string; status: string; original_execution_id: string | null; created_at: string; updated_at: string; }
export interface Indicators {
  generated_at: string;
  source: string;
  organizations: Array<{ id: string; code: string; name: string }>;
  filters: { organization_id: string | null; date_from: string | null; date_to: string | null };
  executions: Record<string, number>;
  workorders: { total?: number; partially_released?: number };
  pending_items: Record<string, number>;
  quantities: { planned?: number; produced?: number; received?: number; released?: number };
}
export interface OperationalEntity { identifier: string; execution_id: string; status: string | null; quantities: Record<string, number | null>; }
export interface PendingItem { id: string; workorder_number: string; category: string; priority: number; status: string; reason: string | null; }
export interface QueryOptions { page?: number; pageSize?: number; sort?: string; filters?: Record<string, string | number | boolean | null | undefined>; }
