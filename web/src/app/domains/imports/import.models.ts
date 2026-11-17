export const importSources = ['N-FP', 'OWM', 'GMES/OQC', 'TMS', 'WO Status', 'Total Decision'] as const;
export type ImportSource = typeof importSources[number];

export interface ImportStatus {
  execution_id: string;
  status: string;
  source: ImportSource;
  file_name: string | null;
  extension: string | null;
  size_bytes: number | null;
  started_at: string;
  finished_at: string | null;
  failure_reason: string | null;
  duplicate_of_execution_id: string | null;
}

export interface FileInspection {
  inspection_id: number;
  source: ImportSource;
  original_file_name: string;
  extension: string | null;
  declared_media_type: string | null;
  detected_media_type: string | null;
  size_bytes: number;
  decision: 'accepted' | 'rejected';
  reason_code: string;
  analyzed_at: string;
  retained_until: string | null;
  discarded_at: string | null;
}

export interface PipelineSummary {
  rows_read: number;
  valid_records: number;
  rejected_records: number;
  normalized_records: number;
  errors: number;
  warnings: number;
}

export interface ImportResultSummary {
  execution_id: string;
  execution_status: string;
  summary_status: 'ready' | 'processing' | 'unavailable' | 'not_applicable';
  summary: PipelineSummary | null;
  issues_total: number;
  generated_at: string;
  reason_code: string;
  inspection_reason_code: string | null;
  duplicate_of_execution_id: string | null;
  /** Response-header metadata, added by the client; absent from the JSON body. */
  correlationId?: string | null;
}

export type ImportIssueSeverity = 'error' | 'warning';
export interface ImportIssue {
  id: number;
  severity: ImportIssueSeverity;
  safe_file_name: string | null;
  sheet_name: string | null;
  row_number: number | null;
  column_name: string | null;
  code: string;
  reason: string;
  scope: 'file' | 'structure' | 'record';
  occurred_at: string;
}

export interface ImportIssuePage {
  items: ImportIssue[];
  pagination: { page: number; page_size: number; total: number; pages: number };
  sort: 'oldest' | 'newest';
  generated_at: string;
}

export interface UploadPolicy {
  source: ImportSource;
  allowed_extensions: string[];
  max_bytes: number;
}

export interface OrganizationOption {
  id: string;
  organization_code: string;
  display_name: string;
}

export interface UploadConfiguration {
  policies: UploadPolicy[];
  organizations: OrganizationOption[];
}

export type UploadState = 'idle' | 'uploading' | 'inspecting' | 'accepted' | 'rejected' | 'duplicate' | 'forbidden' | 'unavailable' | 'error';
export type UploadUpdate =
  | { kind: 'progress'; progress: number | null }
  | { kind: 'complete'; result: ImportStatus };
