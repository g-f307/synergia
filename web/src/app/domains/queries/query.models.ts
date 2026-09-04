export type OperationalEntityType = 'workorder' | 'lot' | 'serial';
export type OperationalSort = 'updated_desc' | 'identifier_asc';

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  pages: number;
}

export interface OperationalSearchItem {
  entity_type: OperationalEntityType;
  identifier: string;
  execution_id: string;
  workorder_number: string;
  lot_number: string | null;
  serial_number: string | null;
  organization_code: string | null;
  processing_status: string | null;
  updated_at: string;
}

export interface OperationalSearchPage {
  items: OperationalSearchItem[];
  pagination: Pagination;
  sort: OperationalSort;
  entity_type: OperationalEntityType;
  query: string;
  source: string;
  generated_at: string;
}

export interface Workorder {
  execution_id: string;
  workorder_number: string;
  organization_code: string | null;
  processing_status: string;
  planned_quantity: number | null;
  produced_quantity: number | null;
  received_quantity: number | null;
  released_quantity: number | null;
  pending_quantity: number | null;
  retained_quantity: number | null;
  partially_released: boolean | null;
  lots: string[];
  serials: string[];
  updated_at: string;
}

export interface Classification {
  classification_id: string;
  rule_id: string;
  state: string;
  entity_type: string;
  entity_id: string;
  justification: string;
  reason: string | null;
  data_quality: string;
  lot_number?: string | null;
  serial_number?: string | null;
}

export interface PendingItem {
  id: number;
  execution_id: string;
  workorder_number: string;
  lot_number: string | null;
  serial_number: string | null;
  category: string;
  reason: string | null;
  status: string;
  priority: string;
  updated_at: string;
}

export interface Provenance {
  field_name: string;
  source: string;
  observed_value: unknown;
  created_at: string;
}

export interface ConsolidatedWorkorder {
  workorder: Workorder;
  classifications: Classification[];
  pending_items: PendingItem[];
  provenance: Provenance[];
}

export interface Lot {
  execution_id: string;
  workorder_number: string;
  lot_number: string;
  serials: string[];
  updated_at: string;
}

export interface Serial {
  execution_id: string;
  workorder_number: string;
  lot_number: string | null;
  serial_number: string;
  container_number: string | null;
  updated_at: string;
}
