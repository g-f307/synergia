export const importSources = ['N-FP', 'OWM', 'GMES/OQC', 'TMS'] as const;
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

export interface UploadPolicy {
  source: ImportSource;
  allowed_extensions: string[];
  max_bytes: number;
}

export type UploadState = 'idle' | 'uploading' | 'inspecting' | 'accepted' | 'rejected' | 'duplicate' | 'forbidden' | 'unavailable' | 'error';
export type UploadUpdate =
  | { kind: 'progress'; progress: number | null }
  | { kind: 'complete'; result: ImportStatus };
