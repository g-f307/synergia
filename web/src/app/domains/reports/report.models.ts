export type ReportType = 'workorder_consolidated' | 'oqc_summary';
export type ReportState = 'generating' | 'succeeded' | 'failed' | 'cancelled';
export type ReportCompleteness = 'complete' | 'partial';
export type ReportSort = 'newest' | 'oldest' | 'type';
export type ReportExportFormat = 'csv' | 'json';

export interface Pagination { page: number; page_size: number; total: number; pages: number; }
export interface OrganizationOption { id: string; organization_code: string; display_name: string; }
export interface ReportTypePolicy { report_type: ReportType; allowed_states: string[]; allowed_filters: string[]; }
export interface ReportPolicy {
  report_types: ReportTypePolicy[];
  export_formats: ReportExportFormat[];
  read_organizations: OrganizationOption[];
  generation_organizations: OrganizationOption[];
  stale_after_seconds: number;
}

export interface ReportFilters {
  date_from?: string;
  date_to?: string;
  state?: string;
  workorder_number?: string;
  lot_number?: string;
  priority?: 'critical' | 'high' | 'normal' | 'low';
}

export interface ReportVersion {
  report_id: string;
  version_id: string;
  version: number;
  report_type: ReportType;
  state: ReportState;
  completeness: ReportCompleteness | null;
  organization_id: string;
  execution_id: string;
  requested_by_user_id: string;
  requested_by_display_name: string | null;
  reference_at: string;
  filters: ReportFilters;
  schema_version: string;
  created_at: string;
  completed_at: string | null;
  failure_code: string | null;
  failure_message: string | null;
  cancellation_reason: string | null;
}

export interface WorkorderReportRow {
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
  serial_count: number;
  open_pending_count: number;
}

export interface OqcReportRow {
  workorder_number: string;
  lot_number: string | null;
  organization_code: string | null;
  decision_state: string;
  reason: string | null;
  pending_item_id?: number | null;
  priority: string | null;
  priority_score: number | null;
  pending_reason: string | null;
  pending_status: string | null;
}

export interface WorkorderReportData { kind: 'workorder_consolidated'; count: number; workorders: WorkorderReportRow[]; }
export interface OqcReportData {
  kind: 'oqc_summary';
  count: number;
  distinct_lots: number;
  by_reason: Record<string, number>;
  by_priority: Record<string, number>;
  by_organization: Record<string, number>;
  items: OqcReportRow[];
}
export type ReportData = WorkorderReportData | OqcReportData;
export interface ReportDetail extends ReportVersion { data: ReportData | null; }
export interface ReportPage { items: ReportVersion[]; pagination: Pagination; sort: string; }

export interface ReportCatalogQuery {
  organizationId?: string;
  reportType?: ReportType;
  state?: ReportState;
  executionId?: string;
  sort: ReportSort;
  page: number;
  pageSize: number;
}

export interface CreateReportPayload {
  report_type: ReportType;
  execution_id: string;
  organization_id: string;
  reference_at: string;
  filters: ReportFilters;
}
