export interface Page<T> { items: T[]; page: number; page_size: number; total: number; }
export interface ImportSummary { execution_id: string; status: string; created_at: string; errors: number; warnings: number; }
export interface ExecutionSummary { id: string; status: string; original_execution_id: string | null; created_at: string; updated_at: string; }
export interface Indicators { workorders: number | null; pending_items: number | null; partial_releases: number | null; generated_at: string; }
export interface OperationalEntity { identifier: string; execution_id: string; status: string | null; quantities: Record<string, number | null>; }
export interface PendingItem { id: string; workorder_number: string; category: string; priority: number; status: string; reason: string | null; }
export interface QueryOptions { page?: number; pageSize?: number; sort?: string; filters?: Record<string, string | number | boolean | null | undefined>; }
