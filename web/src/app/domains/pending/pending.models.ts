export type PendingPriority = 'critical' | 'high' | 'normal' | 'low';
export type PendingSort = 'oldest' | 'newest' | 'category' | 'priority';
export type PendingKind = 'pre-release' | 'post-release' | 'technical' | 'partial' | 'operational';

export interface PendingItem {
  id: number;
  execution_id: string;
  workorder_number: string;
  lot_number: string | null;
  serial_number: string | null;
  category: string;
  reason: string | null;
  status: string;
  priority_score: number;
  priority: PendingPriority;
  responsible_area: string | null;
  classification_id: string | null;
  rule_id: string | null;
  rule_catalog_version: string | null;
  evidence: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface PendingPage {
  items: PendingItem[];
  pagination: { page: number; page_size: number; total: number; pages: number };
  sort: PendingSort;
  generated_at: string;
}

export interface PendingFilters {
  status: string;
  category: string;
  priority: string;
  responsibleArea: string;
  workorderNumber: string;
  lotNumber: string;
  serialNumber: string;
  executionId: string;
  page: number;
  pageSize: number;
  sort: PendingSort;
}
